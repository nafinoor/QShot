from setuptools import setup, find_packages

setup(
    name="qshot",
    version="1.0.0",
    description="Screenshot and Annotation Tool",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Nafi Bin Noor",
    author_email="nafibinnoor@gmail.com",
    py_modules=["QShot"],
    entry_points={
        "console_scripts": [
            "qshot=QShot:main",
        ],
    },
    install_requires=[
        "PyQt6>=6.0",
        "requests>=2.28",
        "Pillow>=9.0",
    ],
    classifiers=[
        "Environment :: X11 Applications :: Qt",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
    ],
    python_requires=">=3.10",
)
