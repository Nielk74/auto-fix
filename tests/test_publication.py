import pytest

from auto_fix.publication import require_verified_pr


def receipt(head):
    return {
        "fromRef": {"id": "refs/heads/auto-fix/candidate", "latestCommit": head},
        "toRef": {"id": "refs/heads/master"},
    }


@pytest.mark.parametrize("head", ["a" * 40, "b" * 64])
def test_complete_git_object_ids_can_identify_verified_candidates(head):
    require_verified_pr(receipt(head), head, "auto-fix/candidate", "master")


@pytest.mark.parametrize("head", [None, "", "a123456", "not-a-git-commit", "g" * 40])
def test_matching_malformed_ids_cannot_invent_verification(head):
    with pytest.raises(RuntimeError, match="full Git commit"):
        require_verified_pr(receipt(head), head, "auto-fix/candidate", "master")
