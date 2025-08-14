#!/usr/bin/env python3
"""
Check durations of subtitle segments to ensure they meet quality standards.
Used by CI/CD pipeline to validate subtitle files.
"""

import sys
import os
import json
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_srt_durations(srt_file):
    """Check if all subtitle segments have appropriate durations."""
    
    if not os.path.exists(srt_file):
        print(f"❌ File not found: {srt_file}")
        return False
    
    issues = []
    total_segments = 0
    short_segments = 0
    long_segments = 0
    
    with open(srt_file, 'r', encoding='utf-8') as f:
        content = f.read()
        segments = content.strip().split('\n\n')
        
        for segment in segments:
            if not segment.strip():
                continue
                
            lines = segment.split('\n')
            if len(lines) < 3:
                continue
                
            total_segments += 1
            
            # Parse timing line
            timing_line = lines[1]
            if ' --> ' in timing_line:
                start_time, end_time = timing_line.split(' --> ')
                
                # Convert to seconds
                def parse_time(time_str):
                    time_str = time_str.replace(',', '.')
                    parts = time_str.split(':')
                    hours = float(parts[0])
                    minutes = float(parts[1])
                    seconds = float(parts[2])
                    return hours * 3600 + minutes * 60 + seconds
                
                start = parse_time(start_time)
                end = parse_time(end_time)
                duration = end - start
                
                # Check duration constraints
                if duration < 0.8:
                    short_segments += 1
                    issues.append(f"Segment {lines[0]}: Duration too short ({duration:.2f}s)")
                elif duration > 8.0:
                    long_segments += 1
                    issues.append(f"Segment {lines[0]}: Duration too long ({duration:.2f}s)")
    
    # Generate report
    print(f"\n📊 Duration Check Report for {os.path.basename(srt_file)}")
    print("=" * 50)
    print(f"Total segments: {total_segments}")
    print(f"Short segments (<0.8s): {short_segments}")
    print(f"Long segments (>8s): {long_segments}")
    print(f"Pass rate: {((total_segments - short_segments - long_segments) / total_segments * 100):.1f}%")
    
    if issues:
        print("\n⚠️ Issues found:")
        for issue in issues[:10]:  # Show first 10 issues
            print(f"  - {issue}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more issues")
    else:
        print("\n✅ All segments have appropriate durations!")
    
    return len(issues) == 0


def main():
    """Main entry point for CI/CD."""
    if len(sys.argv) < 2:
        # Default to checking the production subtitle file
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        srt_file = os.path.join(project_root, "subs", "final_production.srt")
        
        # Fallback to direct version if main doesn't exist
        if not os.path.exists(srt_file):
            srt_file = os.path.join(project_root, "subs", "final_production_direct.srt")
    else:
        srt_file = sys.argv[1]
    
    success = check_srt_durations(srt_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()