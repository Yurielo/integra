# Local development recovery, 2026-09-13

The original Documents checkout could not read `integra_core/documents.py`:
macOS reported `compressed,dataless`, and ordinary file reads waited for the
cloud provider. Its Git objects were also intermittently unavailable.

A fresh checkout was created outside the cloud-managed Documents directory,
from GitHub main `a6f93b43b7b7c943482cace166162ec0bbe171f7`. All thirteen
modified/untracked source files were copied before continuing. The original
checkout and its uncommitted changes were preserved.

The unrelated translation hash/model edits remain in the original checkout.
The recovered review branch uses the verified main VideoText adapter hash;
only the Review/Evidence/Knowledge change is included in its diff.

Pinned SeminarText, VideoText and BookText component checkouts were fetched
from GitHub into the ignored `.runtime-components` directory. No protected
source repository was edited. Locally available alignment dependencies from
the previous application build can be supplied with
`INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES`; the build copies them into its bundle.

For future development, keep the Git working copy and runtime dependencies on
local storage. OneDrive remains a publication target for completed packages.
