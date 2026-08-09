from setuptools import setup, find_packages

setup(
    name="scraper999",
    version="1.0.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "playwright>=1.45.1",
        "fastapi>=0.100.0",
        "uvicorn>=0.22.0",
        "pydantic>=2.0.0"
    ],
    entry_points={
        "console_scripts": [
            "999scraper=scraper999.cli:main",
        ],
    },
)
