import { create } from 'zustand';
import type { PoliceGestureResult } from '../types';

type FrameResult = {
  frame: number;
  time: number;
  raw_time?: number;
  rawTime?: number;
  display_time?: number;
  gesture: string;
  gestureId: number;
  confidence: number;
  keypoints?: number[][];   // 14 [x,y] pairs from pose estimation
  policeOnly?: boolean;
  policeDetected?: boolean;
  policeCandidateDetected?: boolean;
  policeConfirmed?: boolean;
  policeConfirmStreak?: number;
  policeRequiredConfirmFrames?: number;
  policeConfidence?: number;
  policeClass?: string;
  policeBox?: number[];
  policeBoxNorm?: number[];
  policeCandidateConfidence?: number;
  policeCandidateClass?: string;
  policeNegativeConfidence?: number;
  policeNegativeClass?: string;
  policeRejectReason?: string | null;
};

type Segment = {
  start: number;
  end: number;
  gesture: string;
  gestureId: number;
};

type StreamRecord = PoliceGestureResult & {
  inference_ms?: number;
  proposedGesture?: string;
  proposedGestureId?: number;
  proposedConfidence?: number;
  rawGesture?: string;
  rawGestureId?: number;
  rawConfidence?: number;
  singleGesture?: string;
  singleGestureId?: number;
  singleConfidence?: number;
  policeOnly?: boolean;
  policeDetected?: boolean;
  policeCandidateDetected?: boolean;
  policeConfirmed?: boolean;
  policeConfirmStreak?: number;
  policeRequiredConfirmFrames?: number;
  policeConfidence?: number;
  policeClass?: string;
  policeBox?: number[];
  policeBoxNorm?: number[];
  policeCandidateConfidence?: number;
  policeCandidateClass?: string;
  policeNegativeConfidence?: number;
  policeNegativeClass?: string;
  policeRejectReason?: string | null;
  validPose?: boolean;
  poseQuality?: {
    score?: number;
    validUpperKeypoints?: number;
    validArmKeypoints?: number;
  };
};

interface PoliceGestureState {
  // 视频识别结果
  result: PoliceGestureResult | null;
  top5: Array<{ gesture: string; gestureId: number; confidence: number }>;
  frames: FrameResult[];
  segments: Segment[];
  duration: number;
  fps: number;
  sampleFps: number;
  inferenceMs: number;
  videoFileName: string;

  // 实时摄像头
  streamResult: StreamRecord | null;
  streamHistory: StreamRecord[];

  // Actions
  setVideoResult: (data: {
    result: PoliceGestureResult;
    top5: Array<{ gesture: string; gestureId: number; confidence: number }>;
    frames: FrameResult[];
    segments: Segment[];
    duration: number;
    fps: number;
    sampleFps: number;
    inferenceMs: number;
  }) => void;
  setDuration: (d: number) => void;
  setFps: (f: number) => void;
  setSampleFps: (f: number) => void;
  setFrames: (frames: FrameResult[] | ((prev: FrameResult[]) => FrameResult[])) => void;
  setSegments: (segments: Segment[]) => void;
  setInferenceMs: (ms: number) => void;
  setVideoFileName: (name: string) => void;
  setStreamResult: (result: StreamRecord) => void;
  addStreamHistory: (record: StreamRecord) => void;
  clearVideoResult: () => void;
  clearStream: () => void;
}

export const usePoliceGestureStore = create<PoliceGestureState>((set) => ({
  result: null,
  top5: [],
  frames: [],
  segments: [],
  duration: 0,
  fps: 0,
  sampleFps: 0,
  inferenceMs: 0,
  videoFileName: '',
  streamResult: null,
  streamHistory: [],

  setVideoResult: (data) =>
    set({
      result: data.result,
      top5: data.top5,
      frames: data.frames,
      segments: data.segments,
      duration: data.duration,
      fps: data.fps,
      sampleFps: data.sampleFps,
      inferenceMs: data.inferenceMs,
    }),

  setVideoFileName: (name) => set({ videoFileName: name }),
  setDuration: (d) => set({ duration: d }),
  setFps: (f) => set({ fps: f }),
  setSampleFps: (f) => set({ sampleFps: f }),
  setFrames: (frames) =>
    set((state) => ({
      frames: typeof frames === 'function' ? (frames as (prev: FrameResult[]) => FrameResult[])(state.frames) : frames,
    })),
  setSegments: (segments) => set({ segments }),
  setInferenceMs: (ms) => set({ inferenceMs: ms }),

  setStreamResult: (result) => set({ streamResult: result }),

  addStreamHistory: (record) =>
    set((state) => ({
      streamHistory: [record, ...state.streamHistory].slice(0, 10),
    })),

  clearVideoResult: () =>
    set({
      result: null,
      top5: [],
      frames: [],
      segments: [],
      duration: 0,
      fps: 0,
      sampleFps: 0,
      inferenceMs: 0,
      videoFileName: '',
    }),

  clearStream: () =>
    set({
      streamResult: null,
      streamHistory: [],
    }),
}));
