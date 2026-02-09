#!/usr/bin/env python3
"""
Minimal Piece Cache Creator
Creates only piece files without torrent creation
"""
import sys
import os
import time
import json
import hashlib
from pathlib import Path
from typing import Dict, Optional, Tuple
import argparse

class MinimalPieceCacheCreator:
    """Creates only piece files without torrent creation"""
    
    def __init__(self, cache_root: str = "/tmp/.piecache"):
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)
    
    def create_piece_cache(self, source_path: Path, piece_size: int = 1048576) -> Tuple[Path, Dict]:
        """
        Create piece cache - only pieces, no torrent
        """
        print(f"🔨 Creating piece cache for: {source_path}")
        
        if not source_path.is_file():
            print(f"  ⚠  This version only handles single files")
            return None, None
        
        # Get file info
        file_size = source_path.stat().st_size
        file_name = source_path.name
        
        print(f"  File: {file_name}")
        print(f"  Size: {file_size:,} bytes")
        
        # Calculate pieces
        num_pieces = (file_size + piece_size - 1) // piece_size
        print(f"  Pieces: {num_pieces} @ {piece_size:,} bytes each")
        
        # Create cache directory using file hash
        file_hash = self._calculate_file_hash(source_path)
        cache_dir = self.cache_root / file_hash
        cache_dir.mkdir(exist_ok=True)
        
        # Extract and save pieces
        print(f"  Extracting pieces...")
        pieces_saved = 0
        
        with open(source_path, 'rb') as f:
            for piece_index in range(num_pieces):
                # Calculate piece boundaries
                piece_start = piece_index * piece_size
                piece_end = min(piece_start + piece_size, file_size)
                actual_piece_size = piece_end - piece_start
                
                # Read piece
                f.seek(piece_start)
                piece_data = f.read(actual_piece_size)
                
                if piece_data:
                    # Save piece
                    piece_filename = f"piece_{piece_index:06d}.dat"
                    piece_file = cache_dir / piece_filename
                    
                    with open(piece_file, 'wb') as pf:
                        pf.write(piece_data)
                    
                    pieces_saved += 1
                    
                    # Show progress every 10%
                    if piece_index % max(1, num_pieces // 10) == 0:
                        print(f"    Piece {piece_index}/{num_pieces - 1} ({piece_index/num_pieces*100:.0f}%)")
        
        # Create metadata
        metadata = {
            'file_name': file_name,
            'file_size': file_size,
            'file_hash': file_hash,
            'piece_size': piece_size,
            'num_pieces': num_pieces,
            'pieces_saved': pieces_saved,
            'source_path': str(source_path),
            'created_at': time.time()
        }
        
        # Save metadata
        metadata_file = cache_dir / "metadata.txt"
        with open(metadata_file, 'w') as f:
            f.write(f"""Piece Cache Metadata
====================
File: {file_name}
Size: {file_size:,} bytes
Hash: {file_hash}
Piece size: {piece_size:,} bytes
Pieces: {pieces_saved}/{num_pieces}
Created: {time.ctime()}
Source: {source_path}
""")
        
        print(f"\n✅ Piece cache created!")
        print(f"   Cache directory: {cache_dir}")
        print(f"   File hash: {file_hash}")
        print(f"   Pieces saved: {pieces_saved}/{num_pieces}")
        
        return cache_dir, metadata
    
    def _calculate_file_hash(self, filepath: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()[:16]
    
    def list_caches(self):
        """List all caches"""
        print(f"\n📋 Piece Caches in {self.cache_root}:")
        
        cache_dirs = [d for d in self.cache_root.iterdir() if d.is_dir()]
        
        if not cache_dirs:
            print("  No caches found")
            return
        
        for cache_dir in cache_dirs:
            metadata_file = cache_dir / "metadata.txt"
            
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        lines = f.readlines()
                    
                    # Extract info from metadata
                    info = {}
                    for line in lines:
                        if ':' in line:
                            key, value = line.split(':', 1)
                            info[key.strip()] = value.strip()
                    
                    file_name = info.get('File', 'Unknown')
                    file_size = info.get('Size', '0')
                    
                    # Count piece files
                    piece_files = list(cache_dir.glob("piece_*.dat"))
                    
                    print(f"  {cache_dir.name} - {file_name}")
                    print(f"    Size: {file_size}")
                    print(f"    Pieces: {len(piece_files)}")
                    print(f"    Directory: {cache_dir}")
                    print()
                    
                except Exception as e:
                    print(f"  Error reading {cache_dir}: {e}")
    
    def get_cache_info(self, cache_id: str) -> Optional[Dict]:
        """Get cache info"""
        # Try to find by hash
        cache_dir = self.cache_root / cache_id
        if not cache_dir.exists():
            # Try to find by partial hash
            cache_dirs = [d for d in self.cache_root.iterdir() if d.is_dir()]
            for cd in cache_dirs:
                if cd.name.startswith(cache_id):
                    cache_dir = cd
                    cache_id = cd.name
                    break
        
        if not cache_dir.exists():
            print(f"Cache not found: {cache_id}")
            return None
        
        metadata_file = cache_dir / "metadata.txt"
        
        if not metadata_file.exists():
            print(f"Metadata not found for {cache_id}")
            return None
        
        try:
            with open(metadata_file, 'r') as f:
                content = f.read()
            
            # Count files
            piece_files = sorted(list(cache_dir.glob("piece_*.dat")))
            
            return {
                'cache_dir': str(cache_dir),
                'piece_files': len(piece_files),
                'metadata': content
            }
            
        except Exception as e:
            print(f"Error reading cache: {e}")
            return None
    
    def cleanup_cache(self, cache_id: str = None):
        """Clean up cache(s)"""
        import shutil
        
        if cache_id and cache_id != "all":
            cache_dir = self.cache_root / cache_id
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)
                print(f"Cleaned up cache: {cache_id}")
            else:
                print(f"Cache not found: {cache_id}")
        elif cache_id == "all":
            for cache_dir in self.cache_root.iterdir():
                if cache_dir.is_dir():
                    shutil.rmtree(cache_dir, ignore_errors=True)
            print(f"Cleaned up all caches in {self.cache_root}")
        else:
            print("Please specify cache ID or 'all'")

def main():
    parser = argparse.ArgumentParser(
        description="Minimal piece cache creator - creates only piece files"
    )
    parser.add_argument(
        "source", 
        nargs="?", 
        help="Source file to create cache from"
    )
    parser.add_argument(
        "-p", "--piece-size", 
        type=int, 
        default=16384,
        choices=[4096, 8192, 16384, 32768, 65536],
        help="Piece size in bytes (default: 16384)"
    )
    parser.add_argument(
        "-l", "--list", 
        action="store_true",
        help="List all piece caches"
    )
    parser.add_argument(
        "-i", "--info", 
        metavar="ID",
        help="Show info about specific cache"
    )
    parser.add_argument(
        "-c", "--cleanup", 
        metavar="ID",
        nargs="?",
        const="all",
        help="Clean up cache (specific ID or 'all')"
    )
    
    args = parser.parse_args()
    
    creator = MinimalPieceCacheCreator()
    
    if args.list:
        creator.list_caches()
    
    elif args.info:
        cache_info = creator.get_cache_info(args.info)
        if cache_info:
            print(f"\n📊 Cache Info:")
            print(cache_info['metadata'])
            print(f"\n  Directory: {cache_info['cache_dir']}")
            print(f"  Piece files: {cache_info['piece_files']}")
    
    elif args.cleanup:
        creator.cleanup_cache(args.cleanup)
    
    elif args.source:
        source_path = Path(args.source).expanduser()
        
        if not source_path.exists():
            print(f"Error: Source not found: {source_path}")
            sys.exit(1)
        
        if not source_path.is_file():
            print(f"Error: Only single files are supported in minimal version")
            sys.exit(1)
        
        try:
            cache_dir, metadata = creator.create_piece_cache(
                source_path, 
                piece_size=args.piece_size
            )
            
            if cache_dir and metadata:
                # Show first and last few files
                print(f"\n📁 Cache structure:")
                piece_files = sorted(list(cache_dir.glob("piece_*.dat")))
                
                if piece_files:
                    print(f"  {len(piece_files)} piece files:")
                    # Show first 5
                    for pf in piece_files[:5]:
                        size = pf.stat().st_size
                        print(f"    {pf.name} ({size:,} bytes)")
                    
                    if len(piece_files) > 10:
                        print(f"    ...")
                        # Show last 5
                        for pf in piece_files[-5:]:
                            size = pf.stat().st_size
                            print(f"    {pf.name} ({size:,} bytes)")
                    elif len(piece_files) > 5:
                        for pf in piece_files[5:]:
                            size = pf.stat().st_size
                            print(f"    {pf.name} ({size:,} bytes)")
                
                # Show metadata file
                metadata_file = cache_dir / "metadata.txt"
                if metadata_file.exists():
                    size = metadata_file.stat().st_size
                    print(f"  metadata.txt ({size:,} bytes)")
                
                print(f"\n💡 Piece cache ready!")
                print(f"   Directory: {cache_dir}")
                print(f"   Use piece_*.dat files as raw data")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
