"""Setup configuration for WhoopYY package."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="whoopyy",
    version="0.1.0",
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
    install_requires=[
        "httpx>=0.27.0",
        "pydantic>=2.5.0",
        "python-dotenv>=1.0.0",
        "keyring>=24.3.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.12.0",
            "mypy>=1.7.0",
            "ruff>=0.1.8",
        ],
    },
)
