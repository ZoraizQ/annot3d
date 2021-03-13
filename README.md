# 3D Annotation Tool for TIF volumes
Using Python and Tkinter

## Dependencies:
On bash:
```!bash
sudo apt-get install python3-tk python3-pil python3-pil.imagetk 
pip3 install numpy mayavi PyQt5 scikit-image scipy tifffile
```

Windows CMD:
Just install Python from www.python.org/downloads with the tkinter dependency enabled.
```
python -m pip install --upgrade pip
pip install numpy Pillow
```

## Run:
To run the script, just provide the tif image stack filename as the first argument and save mode (RGBA only right now) as second:

```!bash
python3 Annotate.py s07_ROI_cropB.tiff RGBA
python Annotate.py s07_ROI_cropB.tiff RGBA
```
