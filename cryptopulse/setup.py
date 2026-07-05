# -*- coding: utf-8 -*-
from setuptools import find_packages, setup

setup(
    name="cryptopulse",
    version="0.1.0",
    description="CryptoPulse — 单币种智能交易决策系统",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.8",
    install_requires=[
        "pandas>=2.0",
        "numpy>=1.24",
        "loguru>=0.7",
        "websocket-client>=1.7.0",
        "aiohttp>=3.10.0",
        "flask>=2.0",
    ],
    extras_require={
        "full": [
            "python-okx",
            "redis",
        ],
    },
)
