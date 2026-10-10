"""file_baseline rejects Confirm after an out-of-band edit."""
from pathlib import Path

import pytest

from file_baseline import FILE_CHANGED_ON_DISK, reject_if_disk_changed, stamp_baseline
from sdoh_core.requirements_file import RequirementsFileHelper


def test_reject_if_disk_changed_after_edit(tmp_path: Path):
    helper = RequirementsFileHelper(tmp_path)
    helper.write("doc.md", "original\n", confirm=True)
    proposed = stamp_baseline(helper, "doc.md", {"path": "doc.md"})
    helper.write("doc.md", "changed\n", confirm=True)

    with pytest.raises(ValueError, match="changed on disk"):
        reject_if_disk_changed(helper, proposed)
    assert "overwrite" in FILE_CHANGED_ON_DISK
