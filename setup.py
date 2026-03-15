"""Setup configuration for WhoopYY package."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="whoopyy",
    version="0.3.1",
    author="Andrew Ponder",
    author_email="raponder.business@gmail.com",
    description="Complete Python SDK for Whoop API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ponderrr/whoopyy",
    package_dir={"whoopyy": "src"},
    packages=["whoopyy"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP",
        "Typing :: Typed",
    ],
    python_requires=">=3.9",
    keywords=["whoop", "fitness", "health", "api", "sdk", "oauth", "wearable"],
)
