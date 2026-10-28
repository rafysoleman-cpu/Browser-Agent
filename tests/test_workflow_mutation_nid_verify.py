"""
Test script for Mutation Portal NID Verify workflow.

This script tests the WorkflowEngine directly by running the mutation nidVerify workflow.
It uses the existing Playwright browser setup from browser-use.

Usage:
    python tests/test_workflow_mutation_nid_verify.py --nid 1234567890 --day 15 --month 3 --year 1990

Optional arguments:
    --headless   Run browser in headless mode
    --timeout    Max execution time in seconds (default: 300)
"""

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)


async def terminal_ask_human(question: str) -> dict:
    print(f"\n[SYSTEM] {question}")
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, lambda: input("You: ").strip())
    return {"response": response}


async def main():
    parser = argparse.ArgumentParser(description="Test Mutation Portal NID Verify Workflow")
    parser.add_argument("--nid", type=str, required=True, help="NID number for verification")
    parser.add_argument("--day", type=str, required=True, help="Day of birth (1-31)")
    parser.add_argument("--month", type=str, required=True, help="Month of birth (1-12)")
    parser.add_argument("--year", type=str, required=True, help="Year of birth (e.g. 1990)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--timeout", type=int, default=300, help="Max execution time in seconds")
    args = parser.parse_args()

    from src.browser.custom_browser import CustomBrowser
    from browser_use.browser.context import BrowserContextConfig

    logger.info("=" * 70)
    logger.info("MUTATION PORTAL NID VERIFY WORKFLOW TEST")
    logger.info(f"NID: {args.nid}")
    logger.info(f"DOB: {args.day}/{args.month}/{args.year}")
    logger.info(f"Headless: {args.headless}")
    logger.info("=" * 70)

    browser = None
    context = None

    try:
        logger.info("Launching browser...")
        from browser_use.browser.browser import BrowserConfig
        browser = CustomBrowser(
            config=BrowserConfig(
                headless=args.headless,
                disable_security=True,
            )
        )

        context_config = BrowserContextConfig(
            window_width=1280,
            window_height=900,
        )
        context = await browser.new_context(config=context_config)

        page = await context.get_current_page()
        logger.info(f"Browser launched. Page URL: {page.url}")

        from src.workflow.workflow_engine import WorkflowEngine

        engine = WorkflowEngine(
            browser_context=context,
            llm=None,
            ask_human_callback=terminal_ask_human,
            controller=None,
        )

        user_data = {
            "nid_number": args.nid,
            "day": args.day,
            "month": args.month,
            "year": args.year,
        }

        logger.info(f"\nUser data: {user_data}")

        result = await engine.run_workflow(
            site_name="mutation",
            app_name="nidVerify",
            user_data=user_data,
        )

        logger.info("\n" + "=" * 70)
        logger.info("FINAL RESULT:")
        logger.info(f"  Status: {result.get('status', 'unknown')}")
        logger.info(f"  Duration: {result.get('duration_seconds', 0):.2f}s")
        logger.info(f"  Steps executed: {result.get('steps_executed', 0)}")
        logger.info(f"  Selector stats: {result.get('selector_stats', {})}")
        if result.get('extracted_data'):
            logger.info(f"  Extracted data: {result['extracted_data']}")
        if result.get('failed_step'):
            logger.error(f"  Failed at: {result['failed_step']}")
        logger.info("=" * 70)

        return result

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

    finally:
        if context:
            logger.info("Closing browser context...")
            try:
                await context.close()
            except Exception as e:
                logger.warning(f"Error closing context: {e}")
        if browser:
            logger.info("Closing browser...")
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
        logger.info("Test finished")


if __name__ == "__main__":
    result = asyncio.run(main())
    if result.get("status") == "completed":
        logger.info("WORKFLOW TEST PASSED")
        sys.exit(0)
    elif result.get("status") == "error":
        logger.error("WORKFLOW TEST FAILED WITH ERROR")
        sys.exit(1)
    else:
        logger.warning(f"WORKFLOW TEST ENDED WITH STATUS: {result.get('status')}")
        sys.exit(2)
