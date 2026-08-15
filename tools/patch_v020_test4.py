#!/usr/bin/env python3
"""Apply TG Clean v0.2.0 TEST4: media-DC fix + bounded SOCKS diagnostics/storm guard."""
from __future__ import annotations
import pathlib, sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_v020_test4.py <ByeByeDPI checkout>')

root = pathlib.Path(sys.argv[1]).resolve()


def read(rel: str) -> str:
    return (root / rel).read_text(encoding='utf-8')


def write(rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8', newline='\n')


def one(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)


# Installable upgrade over TEST3 and fix the accidental 2.0.0-looking test version label.
gradle_rel = 'app/build.gradle.kts'
t = read(gradle_rel)
t = one(t, 'versionCode = 178022', 'versionCode = 178023', 'TEST4 versionCode')
t = one(t, 'versionName = "2.0.0-tgclean-test3"', 'versionName = "0.2.0-tgclean-test4"', 'TEST4 versionName')
write(gradle_rel, t)

server_rel = 'app/src/main/java/io/github/romanvht/byedpi/ewenloy/tgws/EwenloyTgWsProxyServer.kt'
t = read(server_rel)

# Protect the cached-thread-pool from Telegram retry storms without changing successful traffic.
t = one(
    t,
    'import java.util.concurrent.RejectedExecutionException\n',
    'import java.util.concurrent.RejectedExecutionException\nimport java.util.concurrent.Semaphore\n',
    'Semaphore import',
)
t = one(
    t,
    '    private val stats = Stats()\n',
    '''    private val stats = Stats()
    private val clientSlots = Semaphore(CLIENT_CONCURRENCY_LIMIT)
    private val overloadDrops = AtomicLong(0)
    private val noDcCount = AtomicLong(0)
    private val ipv6Rejected = AtomicLong(0)
    private val blockedSamples = ConcurrentHashMap.newKeySet<String>()
    private val noDcSamples = ConcurrentHashMap.newKeySet<String>()
    private val ipv6Samples = ConcurrentHashMap.newKeySet<String>()
''',
    'TEST4 diagnostic state',
)
t = one(
    t,
    '                Log.i(TAG, "stats: ${stats.summary()}")\n',
    '                Log.i(TAG, "stats: ${stats.summary()} noDc=${noDcCount.get()} ipv6=${ipv6Rejected.get()} overload=${overloadDrops.get()}")\n',
    'extended periodic stats',
)
t = one(
    t,
    '                safeExecute { handleClient(client) }\n',
    '''                if (!clientSlots.tryAcquire()) {
                    overloadDrops.incrementAndGet()
                    runCatching { client.close() }
                    continue
                }
                try {
                    pool.execute {
                        try {
                            handleClient(client)
                        } finally {
                            clientSlots.release()
                        }
                    }
                } catch (_: RejectedExecutionException) {
                    clientSlots.release()
                    runCatching { client.close() }
                }
''',
    'bounded client concurrency',
)

# Keep samples per current network/transport epoch so Mobile and Wi-Fi each produce useful evidence.
t = one(
    t,
    '''        wsPool.clear()
        wsBlacklist.clear()
        lastMode = "idle"
''',
    '''        wsPool.clear()
        wsBlacklist.clear()
        blockedSamples.clear()
        noDcSamples.clear()
        ipv6Samples.clear()
        lastMode = "idle"
''',
    'reset diagnostic samples',
)

# Log only the first unique rejected targets; never log payload/MTProto bytes.
t = one(
    t,
    '''        if (addr.contains(":")) {
            sendReply(output, 0x05); return
        }

        if (!EwenloyTelegramRanges.isTelegramIp(addr)) {
            stats.blockedNonTelegram.incrementAndGet()
            sendReply(output, 0x02)
            return
        }
''',
    '''        if (addr.contains(":")) {
            ipv6Rejected.incrementAndGet()
            logTargetSample("ipv6", addr, port, atyp, ipv6Samples)
            sendReply(output, 0x05)
            return
        }

        if (!EwenloyTelegramRanges.isTelegramIp(addr)) {
            stats.blockedNonTelegram.incrementAndGet()
            logTargetSample("blocked", addr, port, atyp, blockedSamples)
            sendReply(output, 0x02)
            return
        }
''',
    'sample rejected targets',
)

# Ewenloy parser defines negative raw DC IDs as media. The old IP-recovery path had this reversed.
t = one(
    t,
    '                patched = EwenloyMtProtoParser.patchDcId(init, if (isMedia) dc!! else -dc!!)\n',
    '                patched = EwenloyMtProtoParser.patchDcId(init, if (isMedia) -dc!! else dc!!)\n',
    'media DC sign fix',
)

t = one(
    t,
    '''        if (finalDc == null) {
            stats.tcpFallback.incrementAndGet()
            lastMode = "no-dc"; onRouteStatus("no-dc")
            return
        }
''',
    '''        if (finalDc == null) {
            stats.tcpFallback.incrementAndGet()
            noDcCount.incrementAndGet()
            logTargetSample("no-dc", addr, port, atyp, noDcSamples)
            lastMode = "no-dc"; onRouteStatus("no-dc")
            return
        }
''',
    'no-DC target sample',
)

helper_anchor = '''    private fun sendReply(out: OutputStream, code: Int) {
'''
helper = '''    private fun logTargetSample(
        kind: String,
        addr: String,
        port: Int,
        atyp: Int,
        samples: MutableSet<String>,
    ) {
        if (samples.size >= TARGET_SAMPLE_LIMIT) return
        val key = "$atyp|$addr|$port"
        if (samples.add(key)) {
            Log.i(TAG, "target[$kind] atyp=$atyp addr=$addr port=$port")
        }
    }

'''
t = one(t, helper_anchor, helper + helper_anchor, 'target sample helper')

t = one(
    t,
    '''        private const val WARMUP_CONNECT_TIMEOUT_MS = 2_500
''',
    '''        private const val WARMUP_CONNECT_TIMEOUT_MS = 2_500
        private const val CLIENT_CONCURRENCY_LIMIT = 64
        private const val TARGET_SAMPLE_LIMIT = 24
''',
    'TEST4 limits',
)
write(server_rel, t)

# TEST4 invariants.
gradle = read(gradle_rel)
server = read(server_rel)
if 'versionCode = 178023' not in gradle or 'versionName = "0.2.0-tgclean-test4"' not in gradle:
    raise RuntimeError('TEST4 version not applied')
for token in (
    'if (isMedia) -dc!! else dc!!',
    'Semaphore(CLIENT_CONCURRENCY_LIMIT)',
    'target[$kind] atyp=$atyp addr=$addr port=$port',
    'logTargetSample("blocked"',
    'logTargetSample("no-dc"',
    'CLIENT_CONCURRENCY_LIMIT = 64',
    'TARGET_SAMPLE_LIMIT = 24',
):
    if token not in server:
        raise RuntimeError(f'TEST4 invariant missing: {token}')
for forbidden in (
    'if (isMedia) dc!! else -dc!!',
    'directPassthrough(c, input, output, addr, port)',
    'directTcpFallback(c, input, output, addr, port, init)',
):
    if forbidden in server:
        raise RuntimeError(f'TEST4 forbidden transport remains: {forbidden}')
print('TG Clean v0.2.0 TEST4 media-DC/storm diagnostics applied successfully')
