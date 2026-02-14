#!/usr/bin/env python3
"""
Seed Torrent Pieces - Hash-mapped storage
Files are stored by their content hash, mapped during seeding
"""
import sys
import os
import time
import json
import hashlib
import threading
import shutil
import signal
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import argparse

# Try to import libtorrent
lt = None
LIBTORRENT_AVAILABLE = False

def import_libtorrent(custom_path: Optional[str] = None) -> bool:
    global lt, LIBTORRENT_AVAILABLE
    if custom_path:
        try:
            sys.path.insert(0, custom_path)
            import libtorrent as lt
            LIBTORRENT_AVAILABLE = True
            print(f"📚 Using libtorrent from custom path: {custom_path}", file=sys.stderr)
            return True
        except ImportError:
            print(f"⚠️  Could not load libtorrent from custom path", file=sys.stderr)
    try:
        import libtorrent as lt
        LIBTORRENT_AVAILABLE = True
        print("📚 Using system libtorrent", file=sys.stderr)
        return True
    except ImportError:
        print("❌ Error: libtorrent not found", file=sys.stderr)
        return False

class HashMappedSeeder:
    """
    Seeder that stores files by their content hash
    Files in RAM are named by hash, mapped to torrent paths during seeding
    """
    
    def __init__(self, torrent_path: Path, pieces_dir: Path, listen_port: int = 6881):
        self.torrent_path = torrent_path
        self.pieces_dir = pieces_dir
        self.listen_port = listen_port
        self.session = None
        self.handle = None
        self.running = False
        self.peers_info = {}
        self.pieces_served = set()
        self.hash_map = {}  # Maps content hash -> file data
        self.path_map = {}  # Maps torrent path -> content hash
        self.ram_path = None

        # Load torrent
        self.ti = lt.torrent_info(str(torrent_path))
        self.info_hash = str(self.ti.info_hash())
        self.name = self.ti.name()
        self.num_pieces = self.ti.num_pieces()
        self.piece_length = self.ti.piece_length()
        self.total_size = self.ti.total_size()

        # Load metadata from dump_torrent.py output
        self._load_metadata()

        # Load pieces and reconstruct files by hash
        self._load_files_by_hash()

        print(f"\n📊 Torrent Info:")
        print(f"   Name: {self.name or '(empty)'}")
        print(f"   Info Hash: {self.info_hash}")
        print(f"   Files stored by hash: {len(self.hash_map)}")

    def _load_metadata(self):
        """Load metadata from metadata.json to get file root hashes"""
        metadata_file = self.pieces_dir / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    self.metadata = json.load(f)
                print(f"📋 Loaded metadata from: {metadata_file}")
                
                # Build path to hash mapping from metadata
                if 'files' in self.metadata:
                    for file_info in self.metadata['files']:
                        if 'root_hash' in file_info and file_info['root_hash']:
                            self.path_map[file_info['path']] = file_info['root_hash']
                            print(f"   📍 {file_info['path']} -> {file_info['root_hash'][:16]}...")
            except Exception as e:
                print(f"⚠️  Could not load metadata: {e}")
                self.metadata = None
        else:
            print("⚠️  No metadata.json found - will use piece-based reconstruction")
            self.metadata = None

    def _load_files_by_hash(self):
        """Load files from pieces and store by content hash"""
        print(f"\n🔍 Reconstructing files by hash from pieces...")
        
        # First, load all pieces into memory
        pieces_subdir = self.pieces_dir / "pieces"
        if pieces_subdir.exists():
            piece_files = sorted(pieces_subdir.glob("piece_*.dat"))
        else:
            piece_files = sorted(self.pieces_dir.glob("piece_*.dat"))

        if not piece_files:
            print("⚠️  No piece files found!")
            return

        # Load pieces
        piece_data = {}
        print(f"📦 Loading {len(piece_files)} pieces...")
        for pf in piece_files:
            try:
                idx = int(pf.stem.replace('piece_', ''))
                if 0 <= idx < self.num_pieces:
                    data = pf.read_bytes()
                    # Verify hash
                    expected = self.ti.hash_for_piece(idx)
                    if hasattr(expected, 'to_bytes'):
                        expected = expected.to_bytes()[:20]
                    else:
                        expected = bytes(expected)[:20]
                    if hashlib.sha1(data).digest() == expected:
                        piece_data[idx] = data
                        print(f"   ✅ Piece {idx:3d}: {len(data):8,} bytes")
                    else:
                        print(f"   ❌ Piece {idx:3d}: hash mismatch")
            except Exception as e:
                print(f"   ⚠️  Error loading {pf.name}: {e}")

        if not piece_data:
            print("❌ No valid pieces loaded")
            return

        # Reconstruct each file from pieces
        fs = self.ti.files()
        piece_length = self.piece_length

        for i in range(fs.num_files()):
            path = fs.file_path(i)
            size = fs.file_size(i)
            offset = fs.file_offset(i)
            
            print(f"\n   🔨 Reconstructing: {path}")
            
            # Reconstruct file data
            file_data = bytearray(size)
            pieces_used = set()
            
            first_piece = offset // piece_length
            last_piece = (offset + size - 1) // piece_length

            for piece_idx in range(first_piece, last_piece + 1):
                if piece_idx not in piece_data:
                    print(f"      ⚠️  Missing piece {piece_idx}, filling with zeros")
                    continue
                    
                piece_start = piece_idx * piece_length
                piece_end = piece_start + self.ti.piece_size(piece_idx)

                overlap_start = max(offset, piece_start)
                overlap_end = min(offset + size, piece_end)

                if overlap_end > overlap_start:
                    file_pos = overlap_start - offset
                    piece_off = overlap_start - piece_start
                    length = overlap_end - overlap_start
                    
                    file_data[file_pos:file_pos + length] = \
                        piece_data[piece_idx][piece_off:piece_off + length]
                    pieces_used.add(piece_idx)

            # Calculate content hash (SHA256 of the file)
            content_hash = hashlib.sha256(file_data).hexdigest()
            
            # Store by hash
            self.hash_map[content_hash] = bytes(file_data)
            
            # Update path mapping (if not already from metadata)
            if path not in self.path_map:
                self.path_map[path] = content_hash
            
            print(f"      ✅ Stored as: {content_hash[:16]}... (using pieces {sorted(pieces_used)})")

        print(f"\n📦 Total files stored by hash: {len(self.hash_map)}")

    def _create_hash_mapped_fs(self) -> Path:
        """Create filesystem where files are named by their hash"""
        base = Path("/dev/shm") if Path("/dev/shm").exists() else Path("/tmp")
        self.ram_path = Path(tempfile.mkdtemp(dir=base, prefix="torrent_hash_"))
        
        # Set strict permissions
        os.chmod(self.ram_path, 0o700)
        print(f"📁 Hash-mapped storage: {self.ram_path}")

        # Create symlinks from hash-named files to their content
        for content_hash, data in self.hash_map.items():
            hash_file = self.ram_path / content_hash
            with open(hash_file, 'wb') as f:
                f.write(data)
            os.chmod(hash_file, 0o600)
            print(f"   📄 Stored: {content_hash[:16]}... ({len(data)} bytes)")

        # Create mapping file for runtime lookup
        mapping_file = self.ram_path / ".path_mapping.json"
        with open(mapping_file, 'w') as f:
            json.dump(self.path_map, f, indent=2)
        os.chmod(mapping_file, 0o600)

        return self.ram_path

    def _create_symlink_fs(self, hash_dir: Path) -> Path:
        """Create symlinks from torrent paths to hash-named files"""
        link_dir = Path(tempfile.mkdtemp(dir=hash_dir.parent, prefix="torrent_links_"))
        os.chmod(link_dir, 0o700)
        
        print(f"\n🔗 Creating symlink view at: {link_dir}")
        
        fs = self.ti.files()
        for i in range(fs.num_files()):
            path = fs.file_path(i)
            size = fs.file_size(i)
            
            # Find content hash for this path
            content_hash = self.path_map.get(path)
            if not content_hash or content_hash not in self.hash_map:
                print(f"   ⚠️  No hash for {path}, creating sparse file")
                # Create sparse file as fallback
                full_path = link_dir / path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.truncate(size)
                continue
            
            # Create symlink from torrent path to hash-named file
            hash_file = hash_dir / content_hash
            if hash_file.exists():
                full_path = link_dir / path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.symlink_to(hash_file)
                print(f"   🔗 {path} -> {content_hash[:16]}...")
            else:
                print(f"   ❌ Hash file missing: {content_hash[:16]}...")

        return link_dir

    def start(self):
        if not self.hash_map:
            print("❌ No files loaded, aborting.")
            return False

        # Create hash-mapped storage
        hash_dir = self._create_hash_mapped_fs()

        # Create symlink view for libtorrent
        link_dir = self._create_symlink_fs(hash_dir)

        # Create session
        print("\n🌐 Creating session...")
        self.session = lt.session()
        self.running = True

        # Configure
        if hasattr(lt, 'settings_pack'):
            settings = lt.settings_pack()
            settings.listen_interfaces = f'0.0.0.0:{self.listen_port}'
            settings.enable_dht = True
            settings.enable_lsd = True
            settings.enable_upnp = True
            settings.enable_natpmp = True
            self.session.apply_settings(settings)
        else:
            self.session.listen_on(self.listen_port, self.listen_port)
            self.session.start_dht()
            self.session.start_lsd()
            self.session.start_upnp()
            self.session.start_natpmp()

        # Add torrent
        print("\n📥 Adding torrent...")
        atp = lt.add_torrent_params()
        atp.ti = self.ti
        atp.save_path = str(link_dir)  # Point to symlink view
        if hasattr(lt, 'torrent_flags'):
            atp.flags = lt.torrent_flags.default_flags | lt.torrent_flags.upload_mode
        else:
            atp.flags = 0

        self.handle = self.session.add_torrent(atp)
        time.sleep(2)

        if not self.handle.is_valid():
            print("❌ Invalid handle")
            return False

        # Mark pieces as have
        print("\n🔧 Marking pieces...")
        # We need to know which pieces are complete
        # This information is implicit in the files we have
        for piece_idx in range(self.num_pieces):
            try:
                self.handle.have_piece(piece_idx)
                print(f"   ✅ Marked piece {piece_idx}")
            except:
                pass

        # Force re-check
        print("\n🔍 Forcing re-check...")
        self.handle.force_recheck()

        # Wait for check
        for _ in range(30):
            time.sleep(1)
            status = self.handle.status()
            if status.state != lt.torrent_status.checking_files:
                break
            print(f"   Checking... {status.progress*100:.1f}%")

        status = self.handle.status()
        print(f"   State: {status.state}")
        
        if status.state == lt.torrent_status.seeding:
            print("✅ Torrent is SEEDING from hash-mapped storage!")
        elif status.progress >= 0.99:
            print("✅ All pieces present – forcing upload mode")
            if hasattr(lt, 'torrent_flags'):
                self.handle.set_flags(lt.torrent_flags.upload_mode)

        # Start monitoring
        threading.Thread(target=self._monitor_alerts, daemon=True).start()
        threading.Thread(target=self._print_stats_periodic, daemon=True).start()

        print(f"\n🎯 Hash-mapped seeder ready!")
        print(f"   Hash storage: {hash_dir}")
        print(f"   Torrent view: {link_dir}")
        print(f"   Files are stored by SHA256 hash - no original names visible")
        print(f"   Magnet: magnet:?xt=urn:btih:{self.info_hash}")
        return True

    def _monitor_alerts(self):
        while self.running and self.session:
            try:
                alerts = self.session.pop_alerts()
                for alert in alerts:
                    self._handle_alert(alert)
                time.sleep(0.1)
            except:
                pass

    def _handle_alert(self, alert):
        atype = type(alert).__name__
        if atype == 'state_changed_alert' and hasattr(alert, 'state'):
            if alert.state == lt.torrent_status.seeding:
                print("🎯 Now SEEDING!")
        elif atype == 'peer_connect_alert':
            ip = str(getattr(alert, 'ip', 'unknown'))
            self.peers_info[ip] = {'time': time.time(), 'up': 0, 'pieces': set()}
            print(f"🤝 Peer connected: {ip}")
        elif atype == 'peer_disconnected_alert':
            ip = str(getattr(alert, 'ip', 'unknown'))
            if ip in self.peers_info:
                del self.peers_info[ip]
        elif atype == 'piece_finished_alert':
            piece = getattr(alert, 'piece_index', -1)
            self.pieces_served.add(piece)

    def _print_stats_periodic(self):
        while self.running:
            time.sleep(10)
            self._print_stats()

    def _print_stats(self):
        if not self.handle or not self.handle.is_valid():
            return
        s = self.handle.status()
        print("\n" + "="*70)
        print(f"📊 HASH-MAPPED SEEDER - {time.strftime('%H:%M:%S')}")
        print("="*70)
        print(f"Torrent: {self.name}")
        print(f"State: {s.state}  Progress: {s.progress*100:.1f}%")
        print(f"Files by hash: {len(self.hash_map)}")
        print(f"\n📈 Network:")
        print(f"   Peers: {s.num_peers} connected")
        print(f"   Upload: {s.upload_rate/1024:.1f} KB/s")
        print(f"   Uploaded: {s.total_upload/1048576:.2f} MB")
        print(f"   Pieces Served: {len(self.pieces_served)}")
        
        if self.peers_info:
            print(f"\n👥 Connected Peers ({len(self.peers_info)}):")
            for ip, info in list(self.peers_info.items())[:3]:
                duration = time.time() - info['time']
                print(f"   {ip:20} - {duration:4.0f}s")
        print("="*70)

    def stop(self):
        print("\n🛑 Stopping...")
        self.running = False
        time.sleep(1)
        
        if self.handle and self.handle.is_valid():
            try:
                self.session.remove_torrent(self.handle)
                print("✅ Torrent removed")
            except:
                pass
        
        # Clean up
        if self.ram_path and self.ram_path.exists():
            shutil.rmtree(self.ram_path)
            print(f"🧹 Cleaned up {self.ram_path}")
        
        # Also clean up link dir (parent of ram_path)
        link_dir = self.ram_path.parent / "torrent_links_" if self.ram_path else None
        if link_dir and link_dir.exists():
            shutil.rmtree(link_dir)
            print(f"🧹 Cleaned up {link_dir}")
        
        print("✅ Stopped")

def main():
    parser = argparse.ArgumentParser(
        description="Seed torrent from hash-mapped storage - files stored by SHA256 hash"
    )
    parser.add_argument("torrent_file", help="Torrent file")
    parser.add_argument("pieces_dir", help="Directory with pieces")
    parser.add_argument("-p", "--port", type=int, default=6881, help="Listen port")
    parser.add_argument("--libtorrent-path", help="Custom libtorrent path")
    
    args = parser.parse_args()

    if not import_libtorrent(args.libtorrent_path):
        sys.exit(1)

    seeder = HashMappedSeeder(
        Path(args.torrent_file), 
        Path(args.pieces_dir),
        args.port
    )
    
    if seeder.start():
        print("\nCommands: stats, quit")
        
        def signal_handler(sig, frame):
            print("\n\nInterrupted")
            seeder.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        while seeder.running:
            try:
                cmd = input("\n> ").strip().lower()
                if cmd in ('quit','q','exit'):
                    break
                elif cmd == 'stats':
                    seeder._print_stats()
            except EOFError:
                break
        
        seeder.stop()

if __name__ == "__main__":
    main()
