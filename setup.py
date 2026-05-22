from setuptools import setup, find_packages

setup(
    name="quant-pf-signals-bot",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pandas>=2.0",
        "numpy>=1.24",
        "PyYAML>=6.0",
        "python-dotenv>=1.0",
        "yfinance>=0.2",
        "pandas-ta>=0.3.14b",
    ],
)
