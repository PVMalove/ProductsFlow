from kernel_domain.visibility_policy import VisibilityPolicy


class OwnerOnlyPolicy:
    def is_visible(self, viewer: str, resource: str) -> bool:
        return viewer == resource


def test_a_matching_dummy_class_satisfies_the_protocol_structurally() -> None:
    assert isinstance(OwnerOnlyPolicy(), VisibilityPolicy)


def test_a_class_without_a_matching_predicate_does_not_satisfy_it() -> None:
    class NotAPolicy:
        pass

    assert not isinstance(NotAPolicy(), VisibilityPolicy)
