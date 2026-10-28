"""
Test script for Mutation Portal Login workflow.

This script tests the WorkflowEngine directly by running the mutation login workflow.
It uses the existing Playwright browser setup from browser-use.

Usage:
    python tests/test_workflow_mutation_login.py --mobile 1319245792 --password YourPass

If no password is provided, the default "@Aa123456" will be used.
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

# Suppress noisy logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)


async def terminal_ask_human(question: str) -> dict:
    print(f"\n[SYSTEM] {question}")
    response = input("You: ").strip()
    return {"response": response}


async def main():
    parser = argparse.ArgumentParser(description="Test Mutation Portal Login Workflow")
    parser.add_argument("--mobile", type=str, required=True, help="Registered mobile number")
    parser.add_argument("--password", type=str, default="", help="Password (default: @Aa123456)")
    parser.add_argument("--user-type", type=str, default="Citizen", choices=["Citizen", "Organization"],
                        help="User type")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--timeout", type=int, default=120, help="Max execution time in seconds")
    args = parser.parse_args()

    password = args.password if args.password else "@Aa123456"

    from src.browser.custom_browser import CustomBrowser
    from browser_use.browser.context import BrowserContextConfig

    logger.info("=" * 70)
    logger.info("MUTATION PORTAL LOGIN WORKFLOW TEST")
    logger.info(f"Mobile: {args.mobile}")
    logger.info(f"User Type: {args.user_type}")
    logger.info(f"Headless: {args.headless}")
    logger.info("=" * 70)

    browser = None
    context = None

    try:
        logger.info("🚀 Launching browser...")
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
        logger.info(f"✅ Browser launched. Page URL: {page.url}")

        from src.workflow.workflow_engine import WorkflowEngine

        engine = WorkflowEngine(
            browser_context=context,
            llm=None,
            ask_human_callback=terminal_ask_human,
            controller=None,
        )

        user_data = {
            "mobile_number": args.mobile,
            "password": password,
            "user_type": args.user_type,
        }

        logger.info(f"\n📋 User data: {user_data}")

        result = await engine.run_workflow(
            site_name="mutation",
            app_name="login",
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
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

    finally:
        if context:
            logger.info("🧹 Closing browser context...")
            try:
                await context.close()
            except Exception as e:
                logger.warning(f"Error closing context: {e}")
        if browser:
            logger.info("🧹 Closing browser...")
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
        logger.info("🏁 Test finished")


if __name__ == "__main__":
    result = asyncio.run(main())
    if result.get("status") == "completed":
        logger.info("✅ WORKFLOW TEST PASSED")
        sys.exit(0)
    elif result.get("status") == "error":
        logger.error("❌ WORKFLOW TEST FAILED WITH ERROR")
        sys.exit(1)
    else:
        logger.warning(f"⚠️ WORKFLOW TEST ENDED WITH STATUS: {result.get('status')}")
        sys.exit(2)
