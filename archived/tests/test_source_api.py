#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import sys
import os
from typing import Dict, Any

# Add current directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Base URL for API
BASE_URL = "http://localhost:8000/api"

async def test_get_source_types():
    """Test the endpoint to get all source types"""
    print("Testing GET /source-test/source-types")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/source-test/source-types") as response:
            if response.status == 200:
                data = await response.json()
                print(f"Success! Found {len(data)} source types")
                print(f"First 5 sources: {data[:5]}")
            else:
                print(f"Error: {response.status}")
                print(await response.text())

async def test_single_source(source_type: str):
    """Test a single source"""
    print(f"\nTesting GET /source-test/test-source/{source_type}")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/source-test/test-source/{source_type}") as response:
            if response.status == 200:
                data = await response.json()
                print(f"Success! Source test result:")
                print(json.dumps(data, indent=2))
            else:
                print(f"Error: {response.status}")
                print(await response.text())

async def test_all_sources():
    """Test all sources"""
    print("\nTesting GET /source-test/test-all-sources")
    print("This may take a while...")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/source-test/test-all-sources?timeout=30&max_concurrent=5") as response:
            if response.status == 200:
                data = await response.json()
                print(f"Success! All sources test result summary:")
                print(json.dumps(data["summary"], indent=2))
                print(f"\nSuccessful sources: {len(data['successful_sources'])}")
                print(f"Failed sources: {len(data['failed_sources'])}")
                
                if data['failed_sources']:
                    print("\nFailed sources:")
                    for source in data['failed_sources']:
                        print(f"- {source['source_type']}: {source['error']}")
            else:
                print(f"Error: {response.status}")
                print(await response.text())

async def main():
    """Main function"""
    # Get all source types
    await test_get_source_types()
    
    # Test a specific source (you can change this to any source type)
    await test_single_source("bbc")
    
    # Uncomment to test all sources (this may take a while)
    # await test_all_sources()

if __name__ == "__main__":
    asyncio.run(main()) 