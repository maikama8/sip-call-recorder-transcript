# FreePBX

FreePBX already records calls. You do not need
[`examples/extensions_custom.conf`](../examples/extensions_custom.conf) unless
you are adding a custom context. Do not edit `extensions_additional.conf`.
FreePBX regenerates it. Local changes belong in `extensions_custom.conf` or
`extensions_override_freepbx.conf`.

## Where recordings go

The call recording submodule `sub-record-check` writes:

```text
${MIXMON_DIR}${YEAR}/${MONTH}/${DAY}/${CALLFILENAME}.${MON_FMT}
```

`CALLFILENAME` is:

```text
${type}-${destination}-${source}-${TIMESTR}-${UNIQUEID}
```

`TIMESTR` is `YYYYMMDD-HHMMSS`, so a real file looks like:

```text
/var/spool/asterisk/monitor/2026/11/02/internal-102-100-20250116-102939-1737016179.6.wav
```

Read that as: internal call, to extension 102, from extension 100, started
2025-01-16 10:29:39, Asterisk uniqueid `1737016179.6`. The watcher scans
subdirectories, so the `YYYY/MM/DD` layout does not need to be flattened.

| Token | Stored as |
| --- | --- |
| `in`, `external` | inbound |
| `out` | outbound |
| `internal`, `ext` | internal |
| `rg` | ringgroup |
| `q` | queue |

Any other type is kept in lower case, so a newer FreePBX label is not
discarded. The source (`FROMEXTEN`) is the last token before the date and
must not contain a dash. A destination such as `1-800-555-0100` may contain
dashes. `unknown` and `anonymous` are stored as written.

`MIXMON_DIR`, `MIXMON_FORMAT`, and `MIXMON_BEEP` are in **Settings → Advanced
Settings**. `wav` is the useful format here. The browser can play wav and
mp3. gsm is stored and transcribed, but most browsers will not play it. Leave
`MIXMON_POST` alone when FreePBX has set it. This service polls the spool
instead of replacing that hook.

## Recording policy

Set the policy on the extension, the inbound route, or the outbound route.
`Never` on a party stops the recording. `Force` records even when the other
side is `Don't Care`. The UI labels are Force, Yes, Don't Care, No, and
Never. Apply the change and reload the dialplan from FreePBX rather than
from the Asterisk CLI, so the generated dialplan stays in sync.

## CDR

FreePBX stores CDR in MariaDB, database `asteriskcdrdb`, table `cdr`. It does
not write `Master.csv` unless you also load `cdr_csv`. Export a CSV with a
header and point `CDR_PATH` at it, or `POST /cdr` to that path:

```sql
SELECT calldate, clid, src, dst, dcontext, duration, billsec, disposition,
       uniqueid, linkedid, recordingfile, cnum, cnam
FROM cdr
WHERE calldate >= NOW() - INTERVAL 1 DAY;
```

`calldate` is read as the start time. `recordingfile` is the basename
FreePBX stored, and a file that does not parse is still joined when that
basename matches. `cnum` is used when `src` is empty. `linkedid` ties the
legs of one call together and is stored, not used as a primary key. One
uniqueid can appear on more than one channel, so it is an index, not a
uniqueness constraint. `examples/freepbx_cdr.csv` is a one-row export in this
shape.

## Point the service at the PBX

Run the service on the PBX, or mount the spool and a CDR export into the
container. Read-only is enough. The service copies audio into its own
recordings directory before transcribing.

```yaml
services:
  api:
    volumes:
      - /var/spool/asterisk/monitor:/var/spool/asterisk/monitor:ro
      - /var/spool/cdr-export:/cdr:ro
```

Set `CDR_PATH=/cdr/calls.csv` to the export you placed in that directory.
The default compose file uses named volumes so it starts on a laptop.
Replace those with the bind mounts above on a server.

Timestamps are the PBX clock, stored with no timezone. `created_at` is UTC.
The settle window uses the container clock, so a file is ready
`WATCH_SETTLE_SECONDS` after its last write. Five seconds is enough for
MixMonitor, which closes the file when the bridge ends. Raise it if you see
a recording ingested while the call is still up.

## Consent

FreePBX can add a beep through `MIXMON_BEEP` (the dialplan appends it to the
`MixMonitor` options, commonly `B`). Turn that on, or play a recording before
the call is bridged. The legal requirement is yours, not the PBX's. The
README has the longer note.
