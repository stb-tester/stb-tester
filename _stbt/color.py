# coding: utf-8


def get_color(region, frame=None):
    """Get the average color of a region."""

    import stbt

    # Grab a frame if not provided by caller
    frame = stbt.get_frame() if frame is None else frame

    # Extract the requested region
    frame = stbt.crop(frame.copy(), region)

    # Convert the frame to a list and flatten it
    frame = [item for sublist in frame.tolist() for item in sublist]

    # Get total number of pixels
    number_of_pixels = len(frame)

    # Calculate the average color
    blue = green = red = 0
    for pixel in frame:
        blue += pixel[0]
        green += pixel[1]
        red += pixel[2]

    return blue/number_of_pixels, green/number_of_pixels, red/number_of_pixels


def is_color(region, color_range, frame=None):
    """
    Check if the color in a certain part of the screen is within a given range.

    color_range is a tuple with the lowest and highest color values in the range. BGR format.
    Example: ((0, 0, 0), (50, 50, 50))

    """
    return all([
        (c >= color_range[0][i] and c <= color_range[1][i])
        for i, c in enumerate(get_color(region=region, frame=frame))])
