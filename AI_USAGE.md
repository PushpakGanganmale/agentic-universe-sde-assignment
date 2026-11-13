# AI Usage Disclosure

## Tools used

ChatGPT.

## What I used them for

- Discussing assignment requirements and implementation approach.
- Reviewing Python code for ingestion, event processing, database design and encryption.
- Understanding edge cases involving malformed records, duplicate events, orphan reconciliation and idempotency.
- Reviewing test output and preparing submission documentation.

## What I wrote or decided myself

I worked on implementation, integration and execution of the solution. I reviewed the database, normalization, ingestion, encryption and reporting decisions and ran the test suite locally.

## Where the AI was wrong or unhelpful

Some suggested diagnostic steps initially treated malformed JSONL records as possible implementation defects. The assignment explicitly includes malformed event lines as intentional input, so the correct behavior is to count and skip them.

## How I verified AI-generated code

- Reviewed the implementation against the assignment specification.
- Ran `python -m pytest solution/tests -v`.
- Verified that all 45 tests passed.
- Executed the reporting command and inspected the generated report files.
