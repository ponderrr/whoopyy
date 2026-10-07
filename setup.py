"""Setup configuration for the strapkit package."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="strapkit",
    version="0.4.0",
    author="Andrew Ponder",
    author_email="andrew@andrewponder.me",
    description="Unofficial, type-safe Python SDK for the WHOOP Developer API (not affiliated with WHOOP, Inc.)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ponderrr/whoopyy",
    package_dir={"strapkit": "src"},
    packages=["strapkit"],
    package_data={"strapkit": ["py.typed"]},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP",
        "Typing :: Typed",
    ],
    python_requires=">=3.9",
    keywords=["whoop", "fitness", "health", "api", "sdk", "oauth", "wearable"],
)
