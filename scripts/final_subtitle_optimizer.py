#!/usr/bin/env python3
"""
Final subtitle optimizer - achieves the best balance of content accuracy and readability.

Combines the best aspects of all approaches:
1. Preserves original segmentation when quality is good
2. Applies conservative optimization where needed
3. Focus on time extension rather than content restructuring
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.verification.script_checker import load_srt, load_script, generate_report
from src.alignment.conservative_optimizer import conservative_optimize
from src.types import Segment, Word
import unicodedata


def convert_srt_to_segments(srt_segments):
    """Convert SRTSegment to Segment objects."""
    segments = []
    for srt_seg in srt_segments:
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
                        confidence=0.9,
                        source="final_conversion"
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


def precision_time_optimization(segments, max_gap_usage=0.8):
    """
    Precision time optimization - extend display time more aggressively 
    to hit target CPS while preserving content.
    """
    if not segments:
        return []
    
    def _chars_len(text):
        normalized = unicodedata.normalize("NFKC", text or "")
        return len(normalized.replace(" ", "").replace("\u3000", ""))
    
    def _cps(seg):
        dur = max(seg.end - seg.start, 0.001)
        return _chars_len(seg.text or "") / dur
    
    TARGET_CPS = 5.5  # More aggressive target
    MIN_GAP = 0.03    # Smaller gap requirement
    
    result = []
    n = len(segments)
    
    for i, seg in enumerate(segments):
        chars = _chars_len(seg.text or "")
        if chars == 0:
            result.append(seg)
            continue
        
        current_cps = _cps(seg)
        
        # Only optimize if CPS is above target
        if current_cps <= TARGET_CPS:
            result.append(seg)
            continue
        
        # Calculate ideal timing
        ideal_duration = chars / TARGET_CPS
        current_duration = seg.end - seg.start
        
        if ideal_duration <= current_duration:
            result.append(seg)
            continue
        
        # Find available space
        prev_end = segments[i-1].end if i > 0 else 0.0
        next_start = segments[i+1].start if i < n-1 else float('inf')
        
        # Calculate maximum extension within gaps
        gap_before = seg.start - prev_end if i > 0 else 0.0
        gap_after = next_start - seg.end if i < n-1 else float('inf')
        
        # Use up to 80% of available gaps
        usable_before = max(0, gap_before - MIN_GAP) * max_gap_usage
        usable_after = max(0, min(gap_after - MIN_GAP, 2.0)) * max_gap_usage  # Cap after extension
        
        available_extension = usable_before + usable_after
        needed_extension = ideal_duration - current_duration
        
        if available_extension > needed_extension:
            # Distribute extension
            extend_before = min(usable_before, needed_extension * 0.3)  # 30% before
            extend_after = needed_extension - extend_before
            
            new_start = max(prev_end + MIN_GAP, seg.start - extend_before)
            new_end = min(next_start - MIN_GAP, seg.end + extend_after)
            
            optimized_seg = Segment(
                start=new_start,
                end=new_end,
                text=seg.text,
                words=seg.words
            )
            result.append(optimized_seg)
        else:
            # Use all available extension
            new_start = max(prev_end + MIN_GAP, seg.start - usable_before)
            new_end = min(next_start - MIN_GAP, seg.end + usable_after)
            
            optimized_seg = Segment(
                start=new_start,
                end=new_end,
                text=seg.text,
                words=seg.words
            )
            result.append(optimized_seg)
    
    return result


def main():
    print("🎯 Final Subtitle Optimizer")
    print("=" * 50)
    
    # Load data
    script_text = load_script('script_4_2.txt')
    original_srt_segments = load_srt('subs/test_multi.srt')
    
    print(f"📋 Script: {len(script_text)} chars")
    print(f"📋 Original: {len(original_srt_segments)} segments")
    
    # Convert to internal format
    segments = convert_srt_to_segments(original_srt_segments)
    
    # Apply precision time optimization
    print("🔧 Applying precision time optimization...")
    time_optimized = precision_time_optimization(segments)
    
    # Apply conservative structure optimization
    print("🔧 Applying conservative structure optimization...")
    final_segments = conservative_optimize(time_optimized)
    
    print(f"✅ Final: {len(final_segments)} segments")
    
    # Save final result
    output_path = 'subs/final_optimized.srt'
    segments_to_srt_format(final_segments, output_path)
    print(f"💾 Saved: {output_path}")
    
    # Quality analysis
    print(f"\n📊 Final Quality Analysis:")
    print("=" * 40)
    
    final_srt_segments = load_srt(output_path)
    final_report = generate_report(segments=final_srt_segments, script_text=script_text)
    
    # Compare with all versions
    original_report = generate_report(segments=original_srt_segments, script_text=script_text)
    conservative_segments = load_srt('subs/conservative_optimized.srt')
    conservative_report = generate_report(segments=conservative_segments, script_text=script_text)
    
    print("📊 COMPREHENSIVE COMPARISON:")
    print("-" * 50)
    print(f"{'Version':<15} {'Segments':<10} {'Similarity':<10} {'Coverage':<10}")
    print("-" * 50)
    print(f"{'Original':<15} {len(original_srt_segments):<10} {original_report['metrics']['ratio']:<10.3f} {original_report['metrics']['coverage_script']:<10.3f}")
    print(f"{'Conservative':<15} {len(conservative_segments):<10} {conservative_report['metrics']['ratio']:<10.3f} {conservative_report['metrics']['coverage_script']:<10.3f}")
    print(f"{'Final':<15} {len(final_srt_segments):<10} {final_report['metrics']['ratio']:<10.3f} {final_report['metrics']['coverage_script']:<10.3f}")
    
    # Calculate final improvements
    sim_change = final_report['metrics']['ratio'] - original_report['metrics']['ratio']
    cov_change = final_report['metrics']['coverage_script'] - original_report['metrics']['coverage_script']
    
    print(f"\n🎯 Final vs Original:")
    print(f"Similarity change: {sim_change:+.3f}")
    print(f"Coverage change: {cov_change:+.3f}")
    
    if abs(sim_change) < 0.025 and abs(cov_change) < 0.025:
        print("🏆 EXCELLENT: Minimal accuracy loss with timing improvements!")
    elif abs(sim_change) < 0.04 and abs(cov_change) < 0.04:
        print("✅ SUCCESS: Acceptable trade-off for better readability!")
    else:
        print("⚠️ REVIEW: Significant changes - check if improvements justify trade-offs")
    
    # Show key quality metrics
    final_stats = final_report['analysis']['stats']
    print(f"\n📈 Final Quality Metrics:")
    print(f"- Average CPS: {final_stats['avg_cps']:.2f}")
    print(f"- High CPS segments (>6): {sum(1 for s in final_report['analysis']['segments'] if s['cps'] > 6)}")
    print(f"- Short segments (<1s): {sum(1 for s in final_report['analysis']['segments'] if s['duration'] < 1.0)}")
    
    # Determine if this is our best version
    print(f"\n🎉 RECOMMENDATION:")
    if (final_report['metrics']['ratio'] > conservative_report['metrics']['ratio'] and 
        final_report['metrics']['coverage_script'] > conservative_report['metrics']['coverage_script']):
        print("✅ FINAL OPTIMIZED is the BEST version - use this for production!")
    else:
        print("✅ CONSERVATIVE OPTIMIZED remains the best balance - recommended for production")
    
    print(f"\n📋 Detailed Report:")
    print(final_report['report'])


if __name__ == "__main__":
    main()