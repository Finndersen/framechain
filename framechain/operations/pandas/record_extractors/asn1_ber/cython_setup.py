from setuptools import setup
from Cython.Build import cythonize

setup(
    ext_modules = cythonize("asn1_decoder_extensions.pyx", annotate=True, language_level="3")
)