# Asterisk MixMonitor

`MixMonitor` records both directions of a channel into one file. It is the
application to use. The older `Monitor` application writes the directions
separately and is not what this service watches for.

`MixMonitor` does not answer the channel. Call `Answer` or `Progress` first
when the channel is not already up. The recording is an audiohook. Set
`AUDIOHOOK_INHERIT(MixMonitor)=yes` before `MixMonitor` when the call may
pass through a Local channel, or the hook can be dropped when that channel
is optimized away.

A worked dialplan is in [`examples/extensions_custom.conf`](../examples/extensions_custom.conf).
The filename it writes is:

```text
YYYYMMDD-HHMMSS-UNIQUEID-CALLER-CALLEE.wav
20261102-143015-1730554215.23-1001-200.wav
```

`UNIQUEID` is `{epoch}.{sequence}`. If `systemname` is set under `[options]`
in `asterisk.conf`, Asterisk prefixes it and the id becomes
`{systemname}-{epoch}.{sequence}`. Keep `systemname` to letters and digits
so the parser can see it. The same names are listed in
[`examples/filenames.txt`](../examples/filenames.txt).

## Options that matter here

| Option | Effect |
| --- | --- |
| `b` | Write audio only while the channel is bridged. Ringing stays out of the file. On a Local channel, dial with `/n` so the channel is not optimized away before the bridge exists. |
| `B(15)` | Beep every 15 seconds for the duration of the recording. The default interval is 15 seconds when `B` is used alone. |
| `p` / `P` | Beep once when recording starts or stops. |
| `r(file)` | Write only the audio received by this channel. |
| `t(file)` | Write only the audio transmitted by this channel. |
| third argument | A shell command run after the file is closed. |

`r()` and `t()` are the reliable way to know who spoke. Which person is
"receive" depends on the channel you attached `MixMonitor` to. This service
does not join those files yet. One mixed file has no speaker track, which is
why the offline provider labels the bundled sample `caller` and `callee`
instead of pretending to diarize.

`${...}` in the command is expanded when `MixMonitor` is called. `^{VAR}` is
unescaped to `${VAR}` and expanded when the command runs, which is after the
file is closed. Do not pass `CALLERID(num)` or `CALLERID(name)` into that
command. Asterisk treats it as a command-injection risk. Run the value
through `FILTER()` first if you truly need it, and prefer
`^{MIXMONITOR_FILENAME}`, which Asterisk itself generated. The sample
dialplan passes no command. The watcher in this service is enough: it waits
until the file's mtime is `WATCH_SETTLE_SECONDS` old before it copies the
recording.

`StopMixMonitor` is required only when the dialplan itself needs to read the
file before the call ends. The watcher reads the spool after the write has
stopped, so it does not need `StopMixMonitor`.

The dialplan filters the caller id and the extension to `0-9*#+` before they
are placed in the filename. An empty caller id is written as `unknown`.

## Where the file lands

A relative filename is created under the monitor directory from
`asterisk.conf`:

```ini
[directories]
astspooldir => /var/spool/asterisk
```

`MixMonitor` then uses `{astspooldir}/monitor`. The sample dialplan passes an
absolute path, `/var/spool/asterisk/monitor`, so the location does not depend
on that default. Point `MONITOR_DIR` at that directory.

## CDR

`cdr_csv` writes `/var/log/asterisk/cdr-csv/Master.csv`. Load the module from
`modules.conf` (`load = cdr_csv.so`). With no header, the parser expects
Asterisk's default column order:

```text
accountcode,src,dst,dcontext,clid,channel,dstchannel,lastapp,lastdata,
start,answer,end,duration,billsec,disposition,amaflags,uniqueid,userfield
```

A header row is used when it contains `uniqueid` and `src` (or `source`).
`examples/sample_cdr.csv` is one answered call in that shape. Set `CDR_PATH`
to the file. A row with the same `uniqueid` fills the caller, callee, caller
name, times, disposition, and billsec. The filename still wins for direction
when it carries a FreePBX call type.

`billsec` is the talk time stored as `duration_seconds`. A `billsec` of 0 is
kept, including on `NO ANSWER`. When several rows share a uniqueid, the
latest `ANSWERED` row wins.

Direction is only guessed from the context when the filename has no call
type. `from-trunk`, `from-pstn`, `from-did`, `ext-did`, and `from-external`
are inbound. `from-internal` to an extension of at most six digits is
internal; a longer destination is outbound. This matches a stock context
name. A custom context is left blank rather than guessed.

## Consent

`B(15)` is a beep, not a legal review. Many places require all parties to
know they are being recorded, and a beep is not always enough. Play a
recorded warning before the bridge if that is what the jurisdiction
requires. See the privacy note in the README.
