import { create } from 'zustand';
import type { PoliceGestureResult } from '../types';

type FrameResult = {
  frame: number;
  time: number;
  gesture: string;
  gestureId: number;
  confidence: number;
};

type Segment = {
  start: number;
  end: number;
  gesture: string;
  gestureId: number;
};

type StreamRecord = PoliceGestureResult & {
  inference_ms?: number;
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
