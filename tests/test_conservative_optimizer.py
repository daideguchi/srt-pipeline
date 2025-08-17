#!/usr/bin/env python3
"""
Test the conservative optimizer approach.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.verification.script_checker import load_srt, load_script, generate_report
from src.alignment.conservative_optimizer import conservative_optimize, analyze_optimization_impact
from src.types import Segment, Word


def convert_srt_to_segments(srt_segments):
    """Convert SRTSegment objects to Segment objects."""
    segments = []
    for srt_seg in srt_segments:
        # Create basic word timing based on characters
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
                        source="conservative_conversion"
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
    """Save segments as SRT file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments, 1):
            start_time = format_timestamp(seg.start)
            end_time = format_timestamp(seg.end)
            text = seg.text or ''
            
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
    print("🔧 Testing Conservative Optimizer")
    print("=" * 50)
    
    # Load data
    script_text = load_script('script_4_2.txt')
    original_srt_segments = load_srt('subs/test_multi.srt')
    
    print(f"📋 Script: {len(script_text)} chars")
    print(f"📋 Original: {len(original_srt_segments)} segments")
    
    # Convert and optimize
    segments = convert_srt_to_segments(original_srt_segments)
    optimized_segments = conservative_optimize(segments)
    
    print(f"🔧 Optimized: {len(optimized_segments)} segments")
    
    # Save result
    output_path = 'subs/conservative_optimized.srt'
    segments_to_srt_format(optimized_segments, output_path)
    print(f"💾 Saved: {output_path}")
    
    # Analyze optimization impact
    impact = analyze_optimization_impact(segments, optimized_segments)
    
    print(f"\n📊 Optimization Impact:")
    print(f"Segments: {impact['original']['count']} → {impact['optimized']['count']} ({impact['improvements']['segment_change']:+d})")
    print(f"Avg CPS: {impact['original']['avg_cps']:.2f} → {impact['optimized']['avg_cps']:.2f} ({impact['improvements']['cps_improvement']:+.2f})")
    print(f"High CPS (>6.5): {impact['original']['high_cps_count']} → {impact['optimized']['high_cps_count']} ({impact['improvements']['high_cps_reduction']:+d})")
    print(f"Short segments (<1s): {impact['original']['short_count']} → {impact['optimized']['short_count']} ({impact['improvements']['short_reduction']:+d})")
    
    # Quality analysis
    print(f"\n📈 Quality Analysis:")
    print("=" * 30)
    
    conservative_srt_segments = load_srt(output_path)
    report = generate_report(segments=conservative_srt_segments, script_text=script_text)
    
    # Show key metrics only
    metrics = report['metrics']
    print(f"Similarity: {metrics['ratio']:.3f}")
    print(f"Script coverage: {metrics['coverage_script']:.3f}")
    print(f"SRT coverage: {metrics['coverage_srt']:.3f}")
    
    # Compare with original
    original_report = generate_report(segments=original_srt_segments, script_text=script_text)
    original_metrics = original_report['metrics']
    
    print(f"\n🔍 Comparison vs Original:")
    print(f"Similarity: {original_metrics['ratio']:.3f} → {metrics['ratio']:.3f} ({metrics['ratio'] - original_metrics['ratio']:+.3f})")
    print(f"Coverage: {original_metrics['coverage_script']:.3f} → {metrics['coverage_script']:.3f} ({metrics['coverage_script'] - original_metrics['coverage_script']:+.3f})")
    
    # Success criteria
    similarity_loss = original_metrics['ratio'] - metrics['ratio']
    coverage_loss = original_metrics['coverage_script'] - metrics['coverage_script']
    
    if similarity_loss < 0.02 and coverage_loss < 0.02:
        print("✅ SUCCESS: Minimal content accuracy loss with timing improvements!")
        
        # Show detailed improvements
        print(f"\n🎯 Achieved Improvements:")
        if impact['improvements']['cps_improvement'] > 0:
            print(f"- CPS reduced by {impact['improvements']['cps_improvement']:.2f}")
        if impact['improvements']['high_cps_reduction'] > 0:
            print(f"- {impact['improvements']['high_cps_reduction']} fewer high-CPS segments")
        if impact['improvements']['short_reduction'] > 0:
            print(f"- {impact['improvements']['short_reduction']} fewer short segments")
            
    elif similarity_loss < 0.05 and coverage_loss < 0.05:
        print("⚠️ ACCEPTABLE: Minor accuracy trade-off for readability improvements")
    else:
        print("❌ INSUFFICIENT: Too much content accuracy lost")
    
    print(f"\n📋 Full Report:")
    print(report['report'])


if __name__ == "__main__":
    main()