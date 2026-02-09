#!/usr/bin/env python3
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import libtorrent as lt
    print("✓ Successfully imported libtorrent")
    print(f"  Version: {lt.__version__}")
    print(f"  Git revision: {lt.__git_revision__}")
    
    # Create a session to test functionality
    ses = lt.session({'listen_interfaces': '0.0.0.0:6881'})
    print(f"✓ Session created successfully")
    print(f"  Listening on port: {ses.listen_port()}")
    
    # Test piece cache feature (if available in this branch)
    print("\nAvailable session attributes:")
    attrs = [attr for attr in dir(ses) if not attr.startswith('_')]
    print(f"  Found {len(attrs)} attributes")
    
    # Check for piece cache related methods
    piece_cache_attrs = [attr for attr in attrs if 'cache' in attr.lower()]
    if piece_cache_attrs:
        print(f"  Piece cache attributes found: {piece_cache_attrs}")
    
except ImportError as e:
    print(f"✗ Import error: {e}")
    print(f"  Current directory: {os.getcwd()}")
    print(f"  Files here: {os.listdir('.')}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
