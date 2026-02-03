#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import libtorrent as lt

print("=== Exploring Piece Cache Feature ===")
print(f"Libtorrent version: {lt.__version__}")

# List all cache-related items in the module
print("\nAll cache-related items in module:")
for item in sorted(dir(lt)):
    if 'cache' in item.lower() and not item.startswith('_'):
        print(f"  {item}")
        # Try to get more info about it
        obj = getattr(lt, item)
        if hasattr(obj, '__name__'):
            print(f"    Type: {obj.__name__}")
        else:
            print(f"    Type: {type(obj).__name__}")

# Create session and check for cache methods
print("\n\n=== Session Cache Methods ===")
ses = lt.session()

# Get all session methods
session_methods = [m for m in dir(ses) if not m.startswith('_')]

print(f"\nCache-related session methods:")
cache_methods = [m for m in session_methods if 'cache' in m.lower()]
for method in sorted(cache_methods):
    print(f"  {method}")

print(f"\nPiece-related session methods:")
piece_methods = [m for m in session_methods if 'piece' in m.lower()]
for method in sorted(piece_methods):
    print(f"  {method}")

# Check for cache_flushed_alert usage
print("\n\n=== Cache Flushed Alert ===")
print("This alert exists in the module, let's see its structure:")
if hasattr(lt, 'cache_flushed_alert'):
    print("  cache_flushed_alert found in module")
    # Try to see what attributes it has
    try:
        # Check if we can create an alert mask for it
        if hasattr(lt.alert, 'category_t'):
            categories = [attr for attr in dir(lt.alert.category_t) 
                         if not attr.startswith('_')]
            print(f"  Alert categories: {categories[:10]}...")
    except:
        pass

# Test if we can get cache info
print("\n\n=== Testing Cache Info ===")
try:
    # Try different common cache method names
    if hasattr(ses, 'get_cache_info'):
        cache_info = ses.get_cache_info()
        print(f"  get_cache_info() result: {cache_info}")
    elif hasattr(ses, 'cache_status'):
        cache_status = ses.cache_status()
        print(f"  cache_status() result: {cache_status}")
    elif hasattr(ses, 'cache_stats'):
        cache_stats = ses.cache_stats()
        print(f"  cache_stats() result: {cache_stats}")
    else:
        print("  No direct cache info methods found")
        
        # Look for stats that might include cache info
        if hasattr(ses, 'get_stats'):
            stats = ses.get_stats()
            cache_stats_keys = [k for k in stats.keys() if 'cache' in k.lower()]
            if cache_stats_keys:
                print(f"  Found cache-related stats: {cache_stats_keys}")
                for key in cache_stats_keys[:5]:  # Show first 5
                    print(f"    {key}: {stats.get(key, 'N/A')}")
except Exception as e:
    print(f"  Error getting cache info: {e}")

# Check session settings for cache settings
print("\n\n=== Cache-related Settings ===")
try:
    settings = ses.get_settings()
    cache_settings = [k for k in settings.keys() if 'cache' in k.lower()]
    print(f"Found {len(cache_settings)} cache-related settings:")
    for setting in sorted(cache_settings)[:10]:  # Show first 10
        print(f"  {setting}: {settings[setting]}")
except Exception as e:
    print(f"  Error getting settings: {e}")

print("\n=== Test Complete ===")
