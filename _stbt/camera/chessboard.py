from collections import namedtuple
from os.path import dirname

import cv2
import numpy

VIDEO = ('image/png', lambda: [(
    open('%s/chessboard-720p-40px-border-white.png' % dirname(__file__))
    .read(), 60e9)])


class NoChessboardError(Exception):
    pass


def calculate_calibration_params(frame):
    ideal, corners = _find_chessboard(frame)

    undistort = calculate_distortion(ideal, corners, (1920, 1080))
    unperspect = calculate_perspective_transformation(
        ideal, undistort.do(corners))

    return dict(undistort.describe().items() + unperspect.describe().items())


def find_corrected_corners(params, frame):
    ideal, corners = _find_chessboard(frame)
    return ideal, apply_geometric_correction(params, corners)


ReversibleTransformation = namedtuple(
    'ReversibleTransformation', 'do reverse describe')


def calculate_distortion(ideal, measured_points, resolution):
    ideal_3d = numpy.array([[[x, y, 0]] for x, y in ideal],
                           dtype=numpy.float32)
    _, cameraMatrix, distCoeffs, _, _ = cv2.calibrateCamera(
        [ideal_3d], [measured_points], resolution)

    def undistort(points):
        # pylint: disable=E1101
        return cv2.undistortPoints(points, cameraMatrix, distCoeffs)

    def distort(points):
        points = points.reshape((-1, 2))
        points_3d = numpy.zeros((len(points), 3))
        points_3d[:, 0:2] = points
        return cv2.projectPoints(points_3d, (0, 0, 0), (0, 0, 0),
                                 cameraMatrix, distCoeffs)[0]

    def describe():
        return {
            'fx': cameraMatrix[0, 0],
            'fy': cameraMatrix[1, 1],
            'cx': cameraMatrix[0, 2],
            'cy': cameraMatrix[1, 2],

            'k1': distCoeffs[0, 0],
            'k2': distCoeffs[0, 1],
            'p1': distCoeffs[0, 2],
            'p2': distCoeffs[0, 3],
            'k3': distCoeffs[0, 4],
        }
    return ReversibleTransformation(undistort, distort, describe)


def calculate_perspective_transformation(ideal, measured_points):
    ideal_2d = numpy.array([[[x, y]] for x, y in ideal],
                           dtype=numpy.float32)
    mat, _ = cv2.findHomography(measured_points, ideal_2d)
    inv = numpy.linalg.inv(mat)

    def transform_perspective(points):
        return cv2.perspectiveTransform(points, mat)

    def untransform_perspective(points):
        return cv2.perspectiveTransform(points, inv)

    def describe():
        out = {}
        for col in range(3):
            for row in range(3):
                out['ihm%i%i' % (col + 1, row + 1)] = inv[row][col]
        return out
    return ReversibleTransformation(
        transform_perspective, untransform_perspective, describe)


def _find_chessboard(input_image):
    success, corners = cv2.findChessboardCorners(
        input_image, (29, 15), flags=cv2.cv.CV_CALIB_CB_ADAPTIVE_THRESH)

    if not success:
        raise NoChessboardError()

    # Refine the corner measurements (not sure why this isn't built into
    # findChessboardCorners?
    grey_image = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)

    cv2.cornerSubPix(grey_image, corners, (5, 5), (-1, -1),
                     (cv2.TERM_CRITERIA_COUNT, 100, 0.1))

    # Chessboard could have been recognised either way up.  Match it.
    if corners[0][0][0] < corners[1][0][0]:
        ideal = numpy.array(
            [[x * 40 - 0.5, y * 40 - 0.5]
             for y in range(2, 17) for x in range(2, 31)],
            dtype=numpy.float32)
    else:
        ideal = numpy.array(
            [[x * 40 - 0.5, y * 40 - 0.5]
             for y in range(16, 1, -1) for x in range(30, 1, -1)],
            dtype=numpy.float32)

    return ideal, corners


def apply_geometric_correction(params, points):
    # Undistort
    camera_matrix = numpy.array([[params['fx'], 0, params['cx']],
                                 [0, params['fy'], params['cy']],
                                 [0, 0, 1]])
    dist_coeffs = numpy.array(
        [params['k1'], params['k2'], params['p1'], params['p2'], params['k3']])
    points = cv2.undistortPoints(points, camera_matrix, dist_coeffs)

    # Apply perspective transformation:
    mat = numpy.array([[params['ihm11'], params['ihm21'], params['ihm31']],
                       [params['ihm12'], params['ihm22'], params['ihm32']],
                       [params['ihm13'], params['ihm23'], params['ihm33']]])
    return cv2.perspectiveTransform(points, numpy.linalg.inv(mat))[:, 0, :]
