#!/usr/bin/env python3
"""
Seed Torrent Pieces - RAM filesystem seeder
Reconstructs files in tmpfs and seeds from there
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
from typing import Dict, List, Optional, Set
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

class RAMSeeder:
    def __init__(self, torrent_path: Path, pieces_dir: Path, listen_port: int = 6881):
        self.torrent_path = torrent_path
        self.pieces_dir = pieces_dir
        self.listen_port = listen_port
        self.session = None
        self.handle = None
        self.running = False
        self.peers_info = {}
        self.pieces_served = set()
        self.ram_path = None

        # Load torrent
        self.ti = lt.torrent_info(str(torrent_path))
        self.info_hash = str(self.ti.info_hash())
        self.name = self.ti.name()
        self.num_pieces = self.ti.num_pieces()
        self.piece_length = self.ti.piece_length()
        self.total_size = self.ti.total_size()

        # Load pieces into memory
        self.piece_data = self._load_pieces()

        print(f"\n📊 Torrent Info:")
        print(f"   Name: {self.name or '(empty)'}")
        print(f"   Info Hash: {self.info_hash}")
        print(f"   Pieces in memory: {len(self.piece_data)}/{self.num_pieces}")

    def _load_pieces(self) -> Dict[int, bytes]:
        pieces = {}
        pieces_subdir = self.pieces_dir / "pieces"
        if pieces_subdir.exists():
            piece_files = sorted(pieces_subdir.glob("piece_*.dat"))
        else:
            piece_files = sorted(self.pieces_dir.glob("piece_*.dat"))

        if not piece_files:
            print("⚠️  No piece files found!")
            return pieces

        print(f"📦 Loading {len(piece_files)} pieces into memory...")
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
                        pieces[idx] = data
                        print(f"   ✅ Piece {idx:3d}: {len(data):8,} bytes")
                    else:
                        print(f"   ❌ Piece {idx:3d}: hash mismatch")
            except Exception as e:
                print(f"   ⚠️  Error loading {pf.name}: {e}")

        print(f"   Loaded {len(pieces)} pieces")
        return pieces

    def _reconstruct_files_in_ram(self) -> Path:
        """Reconstruct all files in a tmpfs directory."""
        # Use /dev/shm (tmpfs) if available, else fallback to /tmp
        base = Path("/dev/shm") if Path("/dev/shm").exists() else Path("/tmp")
        self.ram_path = Path(tempfile.mkdtemp(dir=base, prefix="torrent_ram_"))
        print(f"📁 Reconstructing files in RAM: {self.ram_path}")

        fs = self.ti.files()
        piece_length = self.piece_length

        for i in range(fs.num_files()):
            path = fs.file_path(i)
            size = fs.file_size(i)
            offset = fs.file_offset(i)
            full_path = self.ram_path / path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Create file (sparse, but we'll write data)
            with open(full_path, 'wb') as f:
                # Determine which pieces belong to this file
                first_piece = offset // piece_length
                last_piece = (offset + size - 1) // piece_length

                for piece_idx in range(first_piece, last_piece + 1):
                    piece_start = piece_idx * piece_length
                    piece_end = piece_start + self.ti.piece_size(piece_idx)

                    # Overlap with this file
                    overlap_start = max(offset, piece_start)
                    overlap_end = min(offset + size, piece_end)

                    if overlap_end > overlap_start:
                        file_pos = overlap_start - offset
                        if piece_idx in self.piece_data:
                            # We have this piece
                            piece_data = self.piece_data[piece_idx]
                            piece_off = overlap_start - piece_start
                            length = overlap_end - overlap_start
                            f.seek(file_pos)
                            f.write(piece_data[piece_off:piece_off + length])
                        else:
                            # Piece missing – fill with zeros
                            f.seek(file_pos)
                            f.write(b'\x00' * (overlap_end - overlap_start))

            print(f"   📄 Reconstructed: {path} ({size} bytes)")

        return self.ram_path

    def start(self):
        if not self.piece_data:
            print("❌ No pieces loaded, aborting.")
            return False

        # Reconstruct files in RAM
        ram_dir = self._reconstruct_files_in_ram()

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
        atp.save_path = str(ram_dir)
        if hasattr(lt, 'torrent_flags'):
            atp.flags = lt.torrent_flags.default_flags | lt.torrent_flags.upload_mode
        else:
            atp.flags = 0

        self.handle = self.session.add_torrent(atp)
        time.sleep(2)

        if not self.handle.is_valid():
            print("❌ Invalid handle")
            return False

        # Mark pieces (redundant but safe)
        print("\n🔧 Marking pieces...")
        for idx in self.piece_data:
            try:
                self.handle.have_piece(idx)
                print(f"   ✅ Marked piece {idx}")
            except:
                pass

        # Set priorities
        try:
            prio = [7 if i in self.piece_data else 0 for i in range(self.num_pieces)]
            self.handle.prioritize_pieces(prio)
        except:
            pass

        # Force re-check (should find all pieces)
        print("\n🔍 Forcing re-check...")
        self.handle.force_recheck()

        # Wait for check to finish
        for _ in range(30):
            time.sleep(1)
            status = self.handle.status()
            if status.state != lt.torrent_status.checking_files:
                break
            print(f"   Checking... {status.progress*100:.1f}%")

        status = self.handle.status()
        print(f"   State: {status.state}")
        if status.state == lt.torrent_status.seeding:
            print("✅ Torrent is SEEDING from RAM!")
        elif status.progress >= 0.99:
            print("✅ All pieces present – forcing upload mode")
            if hasattr(lt, 'torrent_flags'):
                self.handle.set_flags(lt.torrent_flags.upload_mode)
        else:
            print(f"⚠️  State is {status.state}, but we have {len(self.piece_data)} pieces")

        # Start monitoring threads
        threading.Thread(target=self._monitor_alerts, daemon=True).start()
        threading.Thread(target=self._print_stats_periodic, daemon=True).start()

        print(f"\n🎯 RAM seeder ready!")
        print(f"   RAM path: {ram_dir}")
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
            if piece in self.piece_data:
                self.pieces_served.add(piece)
                print(f"📤 Sent piece {piece}")

    def _print_stats_periodic(self):
        while self.running:
            time.sleep(10)
            self._print_stats()

    def _print_stats(self):
        if not self.handle or not self.handle.is_valid():
            return
        s = self.handle.status()
        print("\n" + "="*60)
        print(f"📊 RAM SEEDER - {time.strftime('%H:%M:%S')}")
        print(f"Torrent: {self.name}")
        print(f"State: {s.state}  Progress: {s.progress*100:.1f}%")
        print(f"Pieces: {len(self.piece_data)}/{self.num_pieces} in RAM")
        print(f"Peers: {s.num_peers}  Upload: {s.upload_rate/1024:.1f} KB/s")
        print(f"Uploaded: {s.total_upload/1048576:.2f} MB  Pieces Served: {len(self.pieces_served)}")
        print("="*60)

    def stop(self):
        print("\n🛑 Stopping...")
        self.running = False
        time.sleep(1)
        if self.handle and self.handle.is_valid():
            try:
                self.session.remove_torrent(self.handle)
            except:
                pass
        if self.ram_path and self.ram_path.exists():
            shutil.rmtree(self.ram_path)
            print(f"🧹 Removed {self.ram_path}")
        print("✅ Stopped")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("torrent_file")
    parser.add_argument("pieces_dir")
    parser.add_argument("-p", "--port", type=int, default=6881)
    parser.add_argument("--libtorrent-path")
    args = parser.parse_args()

    if not import_libtorrent(args.libtorrent_path):
        sys.exit(1)

    seeder = RAMSeeder(Path(args.torrent_file), Path(args.pieces_dir), args.port)
    if seeder.start():
        print("\nCommands: stats, quit")
        signal.signal(signal.SIGINT, lambda s,f: seeder.stop() or sys.exit(0))
        while seeder.running:
            try:
                cmd = input("> ").strip().lower()
                if cmd in ('quit','q','exit'):
                    break
                elif cmd == 'stats':
                    seeder._print_stats()
            except EOFError:
                break
        seeder.stop()

if __name__ == "__main__":
    main()
