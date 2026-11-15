"""Manually check domain ages using the real RDAP service."""

import asyncio

import httpx

from mris.rules.domain_age import lookup_domain_age


async def main():
    domains = ["google.com", "example.com", "sait.ca"]

    async with httpx.AsyncClient() as client:
        for domain in domains:
            age = await lookup_domain_age(client, domain)

            if age is None:
                print(f"{domain}: age unknown")
            else:
                print(f"{domain}: {age} days old")


asyncio.run(main())