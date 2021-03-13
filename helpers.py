from PIL import Image
import numpy as np

# from skimage draw
def disk(center, radius, *, shape=None):
  radii = np.array([radius, radius])

  upper_left = np.ceil(center - radii).astype(int)
  upper_left = np.maximum(upper_left, np.array([0, 0]))

  lower_right = np.floor(center + radii).astype(int)
  lower_right = np.minimum(lower_right, np.array(shape[:2]) - 1)

  shifted_center = center - upper_left
  bounding_shape = lower_right - upper_left + 1

  r_lim, c_lim = np.ogrid[0:float(bounding_shape[0]), 0:float(bounding_shape[1])]
  r_org, c_org = shifted_center
  r_rad, c_rad = radii

  r, c = (r_lim - r_org), (c_lim - c_org)
  distances = (r / r_rad) ** 2 + (-c / c_rad) ** 2
  rr, cc = np.nonzero(distances < 1)

  rr.flags.writeable = True
  cc.flags.writeable = True
  rr += upper_left[0]
  cc += upper_left[1]

  return rr, cc



def read_tiff(path): # returns tiff image stack as np array
    img = Image.open(path)
    xy = []
    xz = []
    yz = []

    for i in range(img.n_frames): #x-y plane
        img.seek(i)  
        xy.append(np.array(img))

    xy = np.array(xy)

    for npimg in np.swapaxes(xy, 0, 1): # x with z, x-z plane
        xz.append(npimg)

    for npimg in np.swapaxes(xy, 0, 2): # x with y, y-z plane
        yz.append(npimg)

    return xy, xz, yz


def apply_contrast(npslice, f):
    minval = np.percentile(npslice, f) # vary threshold between 1st and 99th percentiles, when f=1
    maxval = np.percentile(npslice, 100-f)
    result = np.clip(npslice, minval, maxval)
    result = ((result - minval) / (maxval - minval)) * 1024
    return (result).astype(np.short)


def apply_brightness(npslice, f):
    return (npslice*f).astype(np.short)