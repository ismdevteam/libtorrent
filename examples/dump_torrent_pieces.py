#!/usr/bin/env python3
"""
Dump Torrent Pieces - Extract actual piece data from torrent files
"""
import sys
import os
import json
import time
import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
import argparse

# Global for libtorrent
lt = None
LIBTORRENT_AVAILABLE = False

def import_libtorrent(custom_path: Optional[str] = None) -> bool:
    """Import libtorrent, optionally from a custom path"""
    global lt, LIBTORRENT_AVAILABLE
    
    # If custom path is provided, try to import from there first
    if custom_path:
        try:
            sys.path.insert(0, custom_path)
            import libtorrent as lt
            LIBTORRENT_AVAILABLE = True
            print(f"📚 Using libtorrent from custom path: {custom_path}", file=sys.stderr)
            return True
        except ImportError:
            print(f"⚠️  Could not load libtorrent from custom path: {custom_path}", file=sys.stderr)
            print("Falling back to system libtorrent...", file=sys.stderr)
    
    # Try system libtorrent
    try:
        import libtorrent as lt
        LIBTORRENT_AVAILABLE = True
        print("📚 Using system libtorrent", file=sys.stderr)
        return True
    except ImportError:
        print("❌ Error: libtorrent not found in system paths.", file=sys.stderr)
        LIBTORRENT_AVAILABLE = False
        return False

def run_dump_torrent(torrent_file: Path, output_dir: Path, libtorrent_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Run dump_torrent.py to generate metadata.json in the output directory and return the parsed metadata
    """
    # Find dump_torrent.py in the same directory as this script
    script_dir = Path(__file__).parent
    dump_torrent_script = script_dir / "dump_torrent.py"
    
    if not dump_torrent_script.exists():
        print(f"⚠️  Warning: dump_torrent.py not found at {dump_torrent_script}")
        print("   Will generate metadata without it")
        return None
    
    # Build command
    cmd = [sys.executable, str(dump_torrent_script), str(torrent_file), "--pretty"]
    
    # Add libtorrent path if provided
    if libtorrent_path:
        cmd.extend(["--libtorrent-path", libtorrent_path])
    
    print(f"🔧 Running dump_torrent.py to generate metadata...")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the JSON output
        try:
            metadata = json.loads(result.stdout)
            print(f"✅ Metadata loaded from dump_torrent.py")
            return metadata
        except json.JSONDecodeError as e:
            print(f"⚠️  Could not parse dump_torrent.py output as JSON: {e}")
            return None
            
    except subprocess.CalledProcessError as e:
        print(f"⚠️  dump_torrent.py failed with error: {e.stderr}")
        return None
    except Exception as e:
        print(f"⚠️  Error running dump_torrent.py: {e}")
        return None

def extract_pieces(torrent_file: Path, data_dir: Path, output_dir: Path, 
                   libtorrent_path: Optional[str] = None) -> bool:
    """
    Extract all pieces from torrent using actual data files
    """
    print("🎯 Extracting pieces from:", data_dir)
    print("   Torrent:", torrent_file)
    
    if not torrent_file.exists():
        print("❌ Torrent file not found")
        return False
    
    if not data_dir.exists():
        print("❌ Data directory not found")
        return False
    
    if not LIBTORRENT_AVAILABLE:
        print("❌ libtorrent not available")
        return False
    
    try:
        # First, run dump_torrent.py to get accurate metadata
        dump_metadata = run_dump_torrent(torrent_file, output_dir, libtorrent_path)
        
        # Load torrent with libtorrent for piece extraction
        ti = lt.torrent_info(str(torrent_file))
        
        name = ti.name()
        info_hash_v1 = str(ti.info_hash())
        total_size = ti.total_size()
        piece_length = ti.piece_length()
        num_pieces = ti.num_pieces()
        num_files = ti.num_files()
        
        # Use metadata from dump_torrent.py if available
        if dump_metadata:
            print("\n📋 Torrent Info (from dump_torrent.py):")
            if 'info hash v1' in dump_metadata:
                print("   Info Hash v1:", dump_metadata['info hash v1'])
            if 'info hash v2' in dump_metadata and dump_metadata['info hash v2']:
                print("   Info Hash v2:", dump_metadata['info hash v2'])
            if 'name' in dump_metadata:
                print("   Name:", dump_metadata['name'] or "(empty)")
            if 'total size' in dump_metadata:
                print("   Total Size:", f"{dump_metadata['total size']:,}", "bytes")
            if 'piece length' in dump_metadata:
                print("   Piece Size:", f"{dump_metadata['piece length']:,}", "bytes")
            if 'number of pieces' in dump_metadata:
                print("   Number of Pieces:", dump_metadata['number of pieces'])
            if 'number of files' in dump_metadata:
                print("   Number of Files:", dump_metadata['number of files'])
            
            # Update values from dump_metadata if they differ
            if 'total size' in dump_metadata:
                total_size = dump_metadata['total size']
            if 'piece length' in dump_metadata:
                piece_length = dump_metadata['piece length']
            if 'number of pieces' in dump_metadata:
                num_pieces = dump_metadata['number of pieces']
        else:
            print("\n📋 Torrent Info (from libtorrent):")
            print("   Name:", name)
            print("   Info Hash:", info_hash_v1)
            print("   Total Size:", f"{total_size:,}", "bytes")
            print("   Piece Size:", f"{piece_length:,}", "bytes")
            print("   Number of Pieces:", num_pieces)
            print("   Number of Files:", num_files)
        
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        pieces_dir = output_dir / "pieces"
        pieces_dir.mkdir(exist_ok=True)
        
        print("\n💾 Output directory:", output_dir)
        
        # Save dump_metadata to file if we have it
        if dump_metadata:
            metadata_file = output_dir / "metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(dump_metadata, f, indent=2)
            print(f"✅ Metadata saved to: {metadata_file}")
        
        # Get file list
        files = ti.files()
        file_entries = []
        
        for i in range(num_files):
            try:
                # Try modern API
                file_path = files.file_path(i)
                file_size = files.file_size(i)
                file_offset = files.file_offset(i)
            except AttributeError:
                # Fallback
                file_entry = files.at(i)
                file_path = file_entry.path
                file_size = file_entry.size
                file_offset = file_entry.offset
            
            file_entries.append({
                'path': str(file_path),
                'size': file_size,
                'offset': file_offset,
                'is_padding': '.pad/' in str(file_path) or '_____padding_file_' in str(file_path),
            })
        
        # Find actual files
        print("\n🔍 Finding files...")
        actual_files = []
        
        for file_info in file_entries:
            if file_info['is_padding']:
                print(f"   📦 {file_info['path']} (padding)")
                actual_files.append({
                    **file_info,
                    'actual_path': None,
                    'found': True,
                })
                continue
            
            # Try to find the file
            file_found = False
            actual_path = None
            
            # Strategy 1: Direct path
            potential = data_dir / file_info['path']
            if potential.exists():
                file_found = True
                actual_path = potential
            
            # Strategy 2: Without torrent name prefix
            if not file_found and file_info['path'].startswith(name + '/'):
                rel_path = file_info['path'][len(name) + 1:]
                potential = data_dir / rel_path
                if potential.exists():
                    file_found = True
                    actual_path = potential
            
            # Strategy 3: Just filename
            if not file_found:
                filename = Path(file_info['path']).name
                potential = data_dir / filename
                if potential.exists():
                    file_found = True
                    actual_path = potential
            
            # Strategy 4: Recursive search (slow but thorough)
            if not file_found:
                filename = Path(file_info['path']).name
                for root, dirs, files in os.walk(data_dir):
                    if filename in files:
                        file_found = True
                        actual_path = Path(root) / filename
                        break
            
            if file_found:
                actual_size = actual_path.stat().st_size
                if actual_size == file_info['size']:
                    print(f"   ✅ {file_info['path']} ({actual_size:,} bytes)")
                    actual_files.append({
                        **file_info,
                        'actual_path': actual_path,
                        'found': True,
                    })
                else:
                    print(f"   ⚠  {file_info['path']} size mismatch")
                    print(f"      Expected: {file_info['size']:,} bytes")
                    print(f"      Actual: {actual_size:,} bytes")
                    actual_files.append({
                        **file_info,
                        'actual_path': actual_path,
                        'found': False,
                    })
            else:
                print(f"   ❌ {file_info['path']} not found")
                actual_files.append({
                    **file_info,
                    'actual_path': None,
                    'found': False,
                })
        
        # Extract pieces
        print("\n📦 Extracting pieces...")
        
        successful_pieces = 0
        failed_pieces = 0
        
        for piece_idx in range(num_pieces):
            try:
                piece_size = ti.piece_size(piece_idx)
                expected_hash = ti.hash_for_piece(piece_idx).hex()
                piece_start = piece_idx * piece_length
                
                # Build piece data
                piece_data = bytearray()
                current_offset = piece_start
                bytes_remaining = piece_size
                
                while bytes_remaining > 0:
                    # Find file for current offset
                    current_file = None
                    for file_info in actual_files:
                        if file_info['offset'] <= current_offset < file_info['offset'] + file_info['size']:
                            current_file = file_info
                            break
                    
                    if not current_file:
                        raise ValueError(f"No file for offset {current_offset}")
                    
                    # Calculate how much to read from this file
                    offset_in_file = current_offset - current_file['offset']
                    bytes_in_file = current_file['size'] - offset_in_file
                    bytes_to_read = min(bytes_remaining, bytes_in_file)
                    
                    if current_file['is_padding'] or current_file['actual_path'] is None:
                        # Padding or missing file - use zeros
                        piece_data.extend(b'\x00' * bytes_to_read)
                    else:
                        # Read from actual file
                        with open(current_file['actual_path'], 'rb') as f:
                            f.seek(offset_in_file)
                            chunk = f.read(bytes_to_read)
                            piece_data.extend(chunk)
                    
                    bytes_remaining -= bytes_to_read
                    current_offset += bytes_to_read
                
                # Verify size
                if len(piece_data) != piece_size:
                    raise ValueError(f"Wrong size: {len(piece_data)} != {piece_size}")
                
                # Verify hash
                actual_hash = hashlib.sha1(piece_data).hexdigest()
                
                if actual_hash == expected_hash:
                    # Save piece
                    piece_filename = f"piece_{piece_idx:06d}.dat"
                    piece_path = pieces_dir / piece_filename
                    
                    with open(piece_path, 'wb') as f:
                        f.write(piece_data)
                    
                    successful_pieces += 1
                    print(f"   ✅ Piece {piece_idx}: {piece_size:,} bytes")
                else:
                    print(f"   ❌ Piece {piece_idx}: hash mismatch")
                    print(f"      Expected: {expected_hash}")
                    print(f"      Actual: {actual_hash}")
                    failed_pieces += 1
                
                if (piece_idx + 1) % 5 == 0:
                    print(f"   Processed {piece_idx + 1}/{num_pieces} pieces")
                    
            except Exception as e:
                print(f"   ⚠  Piece {piece_idx}: {e}")
                failed_pieces += 1
        
        # Create extraction summary
        extraction_summary = {
            'torrent': str(torrent_file),
            'data_dir': str(data_dir),
            'output_dir': str(output_dir),
            'successful_pieces': successful_pieces,
            'failed_pieces': failed_pieces,
            'total_pieces': num_pieces,
            'extracted_at': time.time(),
        }
        
        # Save extraction summary
        summary_file = output_dir / "extraction_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(extraction_summary, f, indent=2)
        
        # Copy torrent
        torrent_copy = output_dir / torrent_file.name
        shutil.copy2(torrent_file, torrent_copy)
        
        print("\n📊 Results:")
        print("   Successful pieces:", successful_pieces, "/", num_pieces)
        print("   Failed pieces:", failed_pieces)
        print("   Output:", output_dir)
        print("   Metadata from dump_torrent.py:", "✅" if dump_metadata else "❌")
        print("   Extraction summary:", summary_file)
        
        if successful_pieces > 0:
            print(f"\n✅ Extraction complete!")
            return True
        else:
            print("\n❌ No pieces extracted")
            return False
        
    except Exception as e:
        print("❌ Error:", e)
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Extract torrent pieces from actual data files"
    )
    parser.add_argument(
        "torrent",
        help="Torrent file"
    )
    parser.add_argument(
        "data_dir",
        help="Directory containing the data files"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory (default: /tmp/torrent_pieces_<hash>)"
    )
    parser.add_argument(
        "--libtorrent-path",
        help="Custom path to libtorrent Python bindings"
    )
    
    args = parser.parse_args()
    
    torrent_file = Path(args.torrent)
    data_dir = Path(args.data_dir)
    
    # Import libtorrent with custom path if specified
    if not import_libtorrent(args.libtorrent_path):
        print("❌ Error: libtorrent Python bindings not available.", file=sys.stderr)
        print("   Please install libtorrent or specify a custom path with --libtorrent-path", file=sys.stderr)
        sys.exit(1)
    
    if args.output:
        output_dir = Path(args.output)
    else:
        # Create output dir based on torrent hash
        try:
            ti = lt.torrent_info(str(torrent_file))
            # Use v1 hash for directory name (more stable)
            info_hash = str(ti.info_hash())
            if len(info_hash) > 16:
                info_hash = info_hash[:16]
            output_dir = Path(f"/tmp/torrent_pieces_{info_hash}")
        except:
            output_dir = Path(f"/tmp/torrent_pieces_{int(time.time())}")
    
    success = extract_pieces(torrent_file, data_dir, output_dir, args.libtorrent_path)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(1)
    except Exception as e:
        print("\nError:", e)
        sys.exit(1)
