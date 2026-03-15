"""Setup configuration for WhoopYY package."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="whoopyy",
    version="0.2.0",
    author="Robert Ponder",
    author_email="robert.ponder@selu.edu",
    description="Complete Python SDK for Whoop API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ponderrr/whoopyy",
    package_dir={"whoopyy": "src"},
    packages=["whoopyy"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: Other/Proprietary License",
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
    install_requires=[
        "httpx>=0.27.0",
        "pydantic>=2.5.0",
    ],
    extras_require={
        "dev": ["pytest", "pytest-asyncio", "pytest-cov", "mypy", "httpx"],
    },
)
