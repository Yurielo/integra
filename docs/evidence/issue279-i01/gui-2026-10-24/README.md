# I01 resumed native GUI QA — 24 October 2026

Issue #279 / draft PR #280. This evidence supplements the 23 October schema repair and regression report. No product source changed during this continuation.

The previous owned disposable workspace expired while the Mac was locked and was cleaned by its supervisor. A fresh governed disposable build reproduced source `6e6978a5f88930158058df8e90dbe4275f11c29a`, Candidate `candidate-v1-e8064cba8acad3282d86b9d7eea043f85c5eed54ac7db015ccdf089943dee943`, and bundle SHA-256 `1fe98fb2822b50077f78f22db960dc1f457f5b6374736a3dace704e99e8fe7e0`. Bundle validation, actual packaged schema build/save/reopen, native self-test and packaged K2 bridge probe passed again. Post-GUI bundle validation returns the same manifest. The installed app and CURRENT were not used as test outputs.

## Actual native GUI checks

The two-unit synthetic project was prepared with the packaged K1 bridge; its source is intentionally not playable media. In the native app, reviewed evidence and exact source/transcript/word revisions were displayed. Fragment selectors were unchecked by default. Two selected fragments generated concepts/topics. The relation dialog required explicit concept IDs, controlled `associated_with` type and both evidence choices. Every semantic action initially displayed “Выберите решение”.

Five explicit GUI decisions were entered: relation ACCEPT; solar concept EDIT with label `Синтетический GUI термин`; battery concept ACCEPT; battery topic REJECT; solar topic DEFER. Each included a QA rationale and reviewer `synthetic-gui-k2`. The exact package confirmation listed all five decisions and began with its confirmation checkbox off. Only after explicit checkbox selection and application did the native app display “Сохранённая каноническая версия проверена”.

The result has two Concepts, one Relation and zero Topics. Its admitted Knowledge View has three review-decision records; its semantic ledger retains all five decisions, including REJECT/DEFER. The app was quit through its GUI and relaunched with the same isolated root. Reopening showed the edited label and exact relation endpoints/type. Full persisted presentation JSON before/after relaunch is identical at revision `1d8854c426563d66be32696b5051847a5d910fcf16c59c2655c1b65ff864121f`.

A separate isolated copy of the known generated-speech demo was prepared without rerunning Process or models. Native GUI review explicitly admitted its concept/topic as QA decisions. The canonical source button opened the native player dialog with matching quote and hash confirmation at **0.080–5.728 seconds**, words 0–8. A read-only media probe confirms audio/video streams and sufficient duration; the copied media bytes match the source revision hash. The original generated-demo project inventory is unchanged.

This proves native player presentation and exact source navigation. Audible playback was not assessed. CUA coordinate/scroll input returned `noWindowsAvailable`; AX control actions, source dialog capture, saved/reopened views and packaged receipts were available. That automation limitation is not reported as a product playback test. AX text snapshots normalize trailing whitespace for repository checks; original snapshots remain in the local QA evidence directory.

## Outcome and remaining gate

Independent read-only QA reviewed these receipts/screenshots and found no mismatches. All native K2 GUI checks described above passed within the two bounded fixtures. These synthetic/generated-demo choices are **not Product Owner semantic acceptance**. No SeminarText/VideoText source, source-product pin, original project, installed app or CURRENT record changed.

Retained publication remains blocked: all eight full copies are protected/unknown and no terminal copy is eligible for rotation. No ninth retained copy was created and no protected application was retired. No valid candidate-bound Proposal or Owner Test readiness is claimed. The full supported suite remains the previously recorded exact-source run: 1,211 total, 1,143 passed, 64 skipped and four governance failures. CI is red at its governance gate until the archive/proposal handoff is valid; these failures are not relabelled PASS. No implementation change justified repeating that full suite during this evidence-only continuation.

The next product lifecycle decision is whether the prior unaccepted fixed K2 submission under #279 (source `7c4238450398a73fe488b3bdca040e6b53eb23d2`, Candidate `candidate-v1-19e3438fea443e1d917b6575131fd67b47b5f44f71202a6940f85adda12b3b56`) should be superseded by this tested replacement. No supersession, withdrawal or retirement is recorded by this evidence. If authorized, its canonical lifecycle evidence and all existing retirement predicates must pass before governed rotation/publication can proceed. CURRENT promotion and Product Owner semantic acceptance remain separate gates.

Machine-readable outcome: `result.json`. Raw runtime and GUI receipts are retained alongside it.
