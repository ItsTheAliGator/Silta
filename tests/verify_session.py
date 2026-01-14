
import sys
import os
import logging
import time

# Ensure path includes root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from silta.core.session_manager import SessionManager
from silta.gui.peer_browser import PeerBrowserView # Check import

logging.basicConfig(level=logging.DEBUG)

def test_session():
    print("Initializing SessionManager...")
    sm = SessionManager()
    
    print("Starting SessionManager...")
    sm.start()
    
    print("Waiting 2 seconds...")
    time.sleep(2)
    
    print("Stopping SessionManager...")
    sm.stop()
    print("Done.")

if __name__ == "__main__":
    test_session()
