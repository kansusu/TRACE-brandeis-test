import numpy as np
import pytest
from scipy.spatial.transform import Rotation as R

from mmdemo.features.selected_objects.selected_objects_feature import SelectedObjects
from mmdemo.interfaces import (
    ConesInterface,
    ObjectInterface3D,
    SelectedObjectsInterface,
)
from mmdemo.interfaces.data import Cone, GamrTarget, ObjectInfo3D
from tests.utils.fake_feature import FakeFeature


@pytest.fixture(scope="module")
def selected_objects():
    """
    Fixture to load object detector. Only runs once per file.
    """
    so = SelectedObjects(FakeFeature())
    so.initialize()
    yield so
    so.finalize()


@pytest.fixture(
    params=[
        # shift xyz, euler angles
        (np.array([0, 0, 0]), (0, 0, 0)),
        (np.array([0, 0, 0]), (1, 1, 1)),
        (np.array([1, 1, 1]), (0, 0, 0)),
        (np.array([-1, 0, 5]), (3, 0.5, 0.2)),
    ]
)
def transformation(request):
    """
    Specify shift and rotation to perform on cones and points
    """
    trans, euler = request.param
    rot = R.from_euler("xyz", euler).as_matrix()
    return lambda p: np.dot(rot, np.array(p)) + trans


@pytest.fixture
def objects(transformation):
    """
    Create object interface with translated and rotated centers
    """
    centers = [
        (1, 1, 1),
        (1, 0, 1),
        (1, 1, 4),
        (1, 1, 2),
        (4, 1, 0.5),
        (0, 0, 2),
        (0, 0, -1),
    ]
    return ObjectInterface3D(
        [
            ObjectInfo3D(
                p1=(0, 0),
                p2=(0, 0),
                object_class=GamrTarget.RED_BLOCK,
                center=transformation(i),
            )
            for i in centers
        ]
    )


@pytest.mark.parametrize(
    "cone_info,expected",
    [
        ((5, 2, 1), [True, True, False, True, False, True, False]),
        ((5, 0, 4.3), [False, False, True, True, False, True, False]),
        ((1.55, 0, 4.3), [True, True, False, False, False, False, False]),
    ],
)
def test_cone_contains_point(
    cone_info,
    expected: list[bool],
    selected_objects: SelectedObjects,
    objects: ObjectInterface3D,
    transformation,
):
    """
    Check if the feature correctly determines when a cone contains a point.
    For all inputs, rotation and translation are applied to make sure the
    result is invariant.

    Expected values were found by plotting in a 3d graphing calculator.
    """

    length, base_radius, vertex_radius = cone_info

    transformed_cone = Cone(
        base=transformation([0, 0, 0]),
        vertex=transformation([0, 0, length]),
        base_radius=base_radius,
        vertex_radius=vertex_radius,
    )

    out_vals = selected_objects.get_output(
        objects, ConesInterface(cones=[transformed_cone])
    )
    assert isinstance(out_vals, SelectedObjectsInterface)

    assert len(out_vals.objects) == len(
        expected
    ), "The wrong number of objects are returned"

    for (out_obj, out_sel), (expected_obj, expected_sel) in zip(
        out_vals.objects, zip(objects.objects, expected)
    ):
        assert out_obj == expected_obj, "Objects are not as expected"
        assert out_sel == expected_sel, "Object selection is not as expected"


def test_multiple_cones(selected_objects):
    """
    Check that multiple `ConesInterfaces` can be passed to the
    feature and objects will still be selected correctly.
    """

    expected = []
    objects = []
    cones_list = []
    for r in range(10):
        cones = []
        for c in range(10):
            if (r + c) % 3 == 0:
                # create a cone that contains an object
                cones.append(
                    Cone(
                        base=np.array([c, r, 0]),
                        vertex=np.array([c, r, 2]),
                        base_radius=0.1,
                        vertex_radius=0.1,
                    )
                )
                objects.append(
                    ObjectInfo3D(
                        p1=(0, 0),
                        p2=(0, 0),
                        object_class=GamrTarget.RED_BLOCK,
                        center=(c, r, 1),
                    )
                )
                expected.append(True)
            else:
                # create an object with no cone pointing to it
                objects.append(
                    ObjectInfo3D(
                        p1=(0, 0),
                        p2=(0, 0),
                        object_class=GamrTarget.RED_BLOCK,
                        center=(c, r, 1),
                    )
                )
                expected.append(False)

        cones_list.append(ConesInterface(cones=cones))

    out = selected_objects.get_output(ObjectInterface3D(objects=objects), *cones_list)
    assert isinstance(out, SelectedObjectsInterface)

    assert [b for _, b in out.objects] == expected
