from setuptools import setup, find_packages

setup(
    name="evez-sdk",
    version="1.0.0",
    packages=find_packages(),
    install_requires=["requests", "redis"],
    author="EVEZ Team",
    description="Python SDK for EVEZ Platform",
    python_requires=">=3.8"
)
