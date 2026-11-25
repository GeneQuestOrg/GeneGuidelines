"""publish_content_pr refuses a missing reviewer with its own error, before touching the database."""
from __future__ import annotations

import pytest

from backend import content_db
from backend.guideline_pr_publish import GuidelinePrPublishError


@pytest.mark.parametrize("reviewer", [None, "", "   "])
def test_missing_reviewer_raises_the_publish_error(monkeypatch, reviewer):
    def no_database():
        raise AssertionError("the reviewer check must run before any database access")

    monkeypatch.setattr(content_db, "get_connection", no_database)
    with pytest.raises(GuidelinePrPublishError, match="reviewer is required"):
        content_db.publish_content_pr("PR-1", reviewer=reviewer)
