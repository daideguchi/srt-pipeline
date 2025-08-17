#!/usr/bin/env python3
"""
Test the new balanced alignment system for better content accuracy.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.verification.script_checker import load_srt, load_script, generate_report
from src.alignment.smart_segmentation import balanced_alignment
from src.types import Segment, Word


def convert_srt_to_segments(srt_segments):
    """Convert SRTSegment objects to Segment objects with synthesized word timing."""
    segments = []
    for srt_seg in srt_segments:
        # Create character-level words for timing
        words = []
        if srt_seg.text:
            text = srt_seg.text.replace('\n', '')
            char_count = len(text)
            if char_count > 0:
                duration = srt_seg.end - srt_seg.start
                char_duration = duration / char_count
                
                current_time = srt_seg.start
                for char in text:
                    words.append(Word(
                        text=char,
                        start=current_time,
                        end=min(current_time + char_duration, srt_seg.end),
                        confidence=0.8,
                        source="srt_conversion"
                    ))
                    current_time += char_duration
        
        segment = Segment(
            start=srt_seg.start,
            end=srt_seg.end,
            text=srt_seg.text,
            words=words
        )
        segments.append(segment)
    
    return segments


def segments_to_srt_format(segments, output_path):
    """Convert Segment objects back to SRT format."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments, 1):
            start_time = format_timestamp(seg.start)
            end_time = format_timestamp(seg.end)
            text = seg.text.replace('\n', '\n')
            
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{text}\n\n")


def format_timestamp(seconds):
    """Convert seconds to SRT timestamp format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def main():
    print("🎯 Testing Balanced Alignment System")
    print("=" * 50)
    
    # Load original data
    script_text = load_script('script_4_2.txt')
    original_srt_segments = load_srt('subs/test_multi.srt')
    
    print(f"📋 Loaded script: {len(script_text)} characters")
    print(f"📋 Original segments: {len(original_srt_segments)} segments")
    
    # Convert to internal format
    segments = convert_srt_to_segments(original_srt_segments)
    print(f"📋 Converted to {len(segments)} internal segments")
    
    # Apply balanced alignment
    print("\n🔄 Applying balanced alignment...")
    balanced_segments = balanced_alignment(segments, script_text)
    
    print(f"✅ Balanced alignment complete: {len(balanced_segments)} segments")
    
    # Save improved subtitles
    output_path = 'subs/balanced_aligned.srt'
    segments_to_srt_format(balanced_segments, output_path)
    print(f"💾 Saved to: {output_path}")
    
    # Generate quality report
    print("\n📊 Quality Analysis:")
    print("=" * 30)
    
    # Load the newly created SRT for analysis
    balanced_srt_segments = load_srt(output_path)
    report = generate_report(segments=balanced_srt_segments, script_text=script_text)
    
    print(report['report'])
    
    # Compare with original
    original_report = generate_report(segments=original_srt_segments, script_text=script_text)
    
    print(f"\n🔍 COMPARISON:")
    print(f"Original: {len(original_srt_segments)} segments | Similarity: {original_report['metrics']['ratio']:.3f} | Coverage: {original_report['metrics']['coverage_script']:.3f}")
    print(f"Balanced: {len(balanced_srt_segments)} segments | Similarity: {report['metrics']['ratio']:.3f} | Coverage: {report['metrics']['coverage_script']:.3f}")
    
    # Calculate improvements
    similarity_change = report['metrics']['ratio'] - original_report['metrics']['ratio']
    coverage_change = report['metrics']['coverage_script'] - original_report['metrics']['coverage_script']
    
    print(f"📈 Similarity change: {similarity_change:+.3f}")
    print(f"📈 Coverage change: {coverage_change:+.3f}")
    
    if similarity_change > 0 and coverage_change > -0.05:
        print("✅ SUCCESS: Balanced alignment improved quality!")
    elif similarity_change > -0.02 and coverage_change > -0.02:
        print("⚠️ MIXED: Some improvements, minor trade-offs")
    else:
        print("❌ NEEDS WORK: Quality declined, algorithm needs refinement")


if __name__ == "__main__":
    main()