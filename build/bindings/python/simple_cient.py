#!/usr/bin/env python3
import sys
import os
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import libtorrent as lt

class SimpleLibtorrentClient:
    def __init__(self):
        self.ses = lt.session({
            'listen_interfaces': '0.0.0.0:6881',
            'enable_dht': True,
            'enable_upnp': True,
            'enable_natpmp': True,
        })
        print(f"Session created on port {self.ses.listen_port()}")
    
    def create_test_torrent(self):
        """Create a simple test torrent"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, "test_data.bin")
            with open(test_file, "wb") as f:
                f.write(os.urandom(1024 * 10))  # 10KB random data
            
            # Create torrent
            fs = lt.file_storage()
            lt.add_files(fs, tmpdir)
            
            ct = lt.create_torrent(fs)
            ct.set_creator("libtorrent-python-client")
            ct.set_comment("Test torrent")
            
            # Set piece hashes
            lt.set_piece_hashes(ct, tmpdir)
            
            torrent = ct.generate()
            print(f"Created test torrent:")
            print(f"  Info hash: {torrent.info_hash().to_hex()}")
            print(f"  Size: {torrent.total_size()} bytes")
            print(f"  Pieces: {torrent.num_pieces()}")
            
            # Save torrent file
            torrent_data = lt.bencode(ct.generate())
            return torrent_data, torrent
    
    def download_torrent(self, torrent_data, save_path):
        """Download a torrent"""
        # Decode torrent data
        info = lt.torrent_info(torrent_data)
        
        params = {
            'ti': info,
            'save_path': save_path,
        }
        
        handle = self.ses.add_torrent(params)
        print(f"Added torrent: {info.name()}")
        
        # Monitor download
        for i in range(10):
            status = handle.status()
            print(f"Progress: {status.progress * 100:.1f}% | "
                  f"Download: {status.download_rate / 1000:.1f} kB/s | "
                  f"Peers: {status.num_peers}")
            time.sleep(1)
            
            if status.progress == 1.0:
                print("Download complete!")
                break
    
    def check_cache_features(self):
        """Check for piece cache related features"""
        print("\n=== Checking Cache Features ===")
        
        # Get session stats
        stats = self.ses.get_stats()
        print("Session stats keys (cache-related):")
        cache_stats = [k for k in stats.keys() if 'cache' in k.lower()]
        for key in cache_stats:
            print(f"  {key}: {stats[key]}")
        
        # Check alerts
        self.ses.set_alert_mask(lt.alert.category_t.all_categories)
        print("\nWaiting for alerts...")
        time.sleep(2)
        
        alerts = self.ses.pop_alerts()
        print(f"Got {len(alerts)} alerts")
        for alert in alerts:
            alert_type = type(alert).__name__
            if 'cache' in alert_type.lower():
                print(f"  Cache alert: {alert_type} - {alert.message()}")

def main():
    client = SimpleLibtorrentClient()
    
    # Create and download a test torrent
    print("\n=== Creating test torrent ===")
    torrent_data, torrent = client.create_test_torrent()
    
    print("\n=== Downloading test torrent ===")
    client.download_torrent(torrent_data, "/tmp/libtorrent_download")
    
    # Check cache features
    client.check_cache_features()

if __name__ == "__main__":
    main()
