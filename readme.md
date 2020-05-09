# Video Annotation
Roberto Negro #211505\
Fundamentals of Video and Image Processing\
Università degli Studi di Trento a.a. 2019/20

# Dependencies
* Python 3.6
* pip install numpy Pygments coloredlogs PySide2 opencv-python-headless qimage2ndarray fbs pyinstaller==3.4
Tested on Mac OS High Sierra (10.13.6) and Mac OS Mojave (10.15.4) with .mp4 and .avi files

# Executing and compiling
Execute: fbs run
Compile: fbs freeze or fbs release

# Troubleshooting
If "Can not find path ./libshiboken2.abi3.5.14.dylib" error on fbs freeze, copy ~/.conda/envs/<YOUR_ENV>/lib/python3.6/site-packages/shiboken2/libshiboken2.abi3.5.14.dylib to .../site-packages/PyInstaller/hooks/ and .../site-packages/PySide2/