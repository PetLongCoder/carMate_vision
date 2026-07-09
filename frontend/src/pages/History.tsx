import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, Table, Tag, Space, Segmented, Empty, message, Spin, Collapse } from 'antd';
import { CameraOutlined, HighlightOutlined, AimOutlined, VideoCameraOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/common';
import { getHistory } from '../api';
import dayjs from 'dayjs';

// ---- Mock 数据 (车牌识别 / 车主手势暂未接入真实数据库) ----
const mockPlateHistory: HistoryItem[] = [
  { id: 1001, type: 'plate', result: { plateNo: '沪A12345', color: 'blue' }, createdAt: dayjs().subtract(10, 'minute').toISOString() },
  { id: 1002, type: 'plate', result: { plateNo: '京B67890', color: 'green' }, createdAt: dayjs().subtract(2, 'hour').toISOString() },
];
const mockDriverHistory: HistoryItem[] = [
  { id: 2001, type: 'driver_gesture', result: { gesture: '音量调高', controlType: 'volume_up' }, createdAt: dayjs().subtract(25, 'minute').toISOString() },
  { id: 2002, type: 'driver_gesture', result: { gesture: '下一首', controlType: 'next_track' }, createdAt: dayjs().subtract(3, 'hour').toISOString() },
];

// ---- 类型定义 ----
interface HistoryItem {
  id: number;
  type: string;
  result: Record<string, unknown>;
  // 交警手势扩展字段
  recognitionType?: string;
  videoSessionId?: string;
  filename?: string;
  gesture?: string;
  gestureId?: number;
  confidence?: number;
  segments?: Array<{ start: number; end: number; gesture: string; gestureId: number }>;
  videoDuration?: number;
  framesTotal?: number;
  framesProcessed?: number;
  videoFps?: number;
  inferenceMs?: number;
  success?: boolean;
  createdAt: string;
}

// 视频分组: 同一 videoSessionId 的段归为一组
interface VideoGroup {
  videoSessionId: string;
  filename: string;
  videoDuration?: number;
  framesTotal?: number;
  framesProcessed?: number;
  videoFps?: number;
  inferenceMs?: number;
  createdAt: string;
  segments: HistoryItem[];
}

const typeConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  plate: { color: 'blue', icon: <CameraOutlined />, label: '车牌识别' },
  police_gesture: { color: 'purple', icon: <HighlightOutlined />, label: '交警手势' },
  driver_gesture: { color: 'green', icon: <AimOutlined />, label: '车主手势' },
};

type FilterType = 'all' | 'plate' | 'police_gesture' | 'driver_gesture';

const GESTURE_COLORS: Record<number, string> = {
  0: '#8c8c8c', 1: '#f5222d', 2: '#1677ff', 3: '#722ed1',
  4: '#eb2f96', 5: '#fa8c16', 6: '#52c41a', 7: '#faad14', 8: '#13c2c2',
};

const History: React.FC = () => {
  const [filter, setFilter] = useState<FilterType>('all');
  const [gestureData, setGestureData] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const fetchGestureHistory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getHistory({ page, pageSize, type: 'gesture' });
      const rawList = (res.data.data as any).list || [];
      const list: HistoryItem[] = rawList.map((item: any) => ({
        id: item.id,
        type: 'police_gesture',
        result: { gesture: item.gesture, confidence: item.confidence },
        recognitionType: item.recognitionType,
        videoSessionId: item.videoSessionId,
        filename: item.filename,
        gesture: item.gesture,
        gestureId: item.gestureId,
        confidence: item.confidence,
        segments: item.segments,
        videoDuration: item.videoDuration,
        framesTotal: item.framesTotal,
        framesProcessed: item.framesProcessed,
        videoFps: item.videoFps,
        inferenceMs: item.inferenceMs,
        success: item.success,
        createdAt: item.createdAt,
      }));
      setGestureData(list);
    } catch (err) {
      console.error('获取交警手势历史失败:', err);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    fetchGestureHistory();
  }, [fetchGestureHistory]);

  // 将视频类型的记录按 videoSessionId 分组
  const videoGroups = useMemo<VideoGroup[]>(() => {
    const groupMap = new Map<string, HistoryItem[]>();
    const singles: HistoryItem[] = [];

    gestureData.forEach((item) => {
      if (item.videoSessionId && (item.recognitionType === 'video' || item.recognitionType === 'video_stream')) {
        const existing = groupMap.get(item.videoSessionId);
        if (existing) {
          existing.push(item);
        } else {
          groupMap.set(item.videoSessionId, [item]);
        }
      } else {
        singles.push(item);
      }
    });

    const groups: VideoGroup[] = [];
    groupMap.forEach((items, sessionId) => {
      const first = items[0];
      groups.push({
        videoSessionId: sessionId,
        filename: first.filename || '未知视频',
        videoDuration: first.videoDuration,
        framesTotal: first.framesTotal,
        framesProcessed: first.framesProcessed,
        videoFps: first.videoFps,
        inferenceMs: first.inferenceMs,
        createdAt: first.createdAt,
        segments: items.sort((a, b) => {
          const aStart = a.segments?.[0]?.start ?? 0;
          const bStart = b.segments?.[0]?.start ?? 0;
          return aStart - bStart;
        }),
      });
    });

    // 按时间倒序
    groups.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

    return groups;
  }, [gestureData]);

  // 非视频的单条记录 (图片/摄像头)
  const singleItems = useMemo(() => {
    return gestureData.filter(
      (item) => !item.videoSessionId || (item.recognitionType !== 'video' && item.recognitionType !== 'video_stream')
    ).sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }, [gestureData]);

  // 合并所有数据源: mock + 分组视频 + 单条
  const displayItems = useMemo(() => {
    const items: Array<{ type: 'mock_plate' | 'mock_driver' | 'video_group' | 'single'; data: any }> = [];

    if (filter === 'all' || filter === 'plate') {
      mockPlateHistory.forEach((m) => items.push({ type: 'mock_plate', data: m }));
    }
    if (filter === 'all' || filter === 'driver_gesture') {
      mockDriverHistory.forEach((m) => items.push({ type: 'mock_driver', data: m }));
    }
    if (filter === 'all' || filter === 'police_gesture') {
      videoGroups.forEach((g) => items.push({ type: 'video_group', data: g }));
      singleItems.forEach((s) => items.push({ type: 'single', data: s }));
    }

    items.sort((a, b) => {
      const aTime = a.type === 'video_group' ? a.data.createdAt :
                    a.type === 'single' ? a.data.createdAt :
                    a.data.createdAt;
      const bTime = b.type === 'video_group' ? b.data.createdAt :
                    b.type === 'single' ? b.data.createdAt :
                    b.data.createdAt;
      return new Date(bTime).getTime() - new Date(aTime).getTime();
    });

    return items;
  }, [filter, videoGroups, singleItems]);

  return (
    <div>
      <PageHeader title="历史记录" subtitle="查看车牌识别、手势识别的历史操作记录" />
      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Segmented
            options={[
              { label: '全部', value: 'all' },
              { label: '车牌识别', value: 'plate' },
              { label: '交警手势', value: 'police_gesture' },
              { label: '车主手势', value: 'driver_gesture' },
            ]}
            value={filter}
            onChange={(v) => { setFilter(v as FilterType); setPage(1); }}
          />
        </Space>
        <Spin spinning={loading}>
          {displayItems.length > 0 ? (
            <div>
              {displayItems.map((item, idx) => {
                // 车牌识别 mock
                if (item.type === 'mock_plate') {
                  const d = item.data as HistoryItem;
                  return (
                    <Card key={`plate-${d.id}`} size="small" style={{ marginBottom: 8 }}>
                      <Space>
                        <Tag color="blue" icon={<CameraOutlined />}>车牌识别</Tag>
                        <Tag style={{ fontSize: 14 }}>{d.result.plateNo as string}</Tag>
                        <span style={{ color: '#8c8c8c' }}>{dayjs(d.createdAt).format('YYYY-MM-DD HH:mm:ss')}</span>
                      </Space>
                    </Card>
                  );
                }
                // 车主手势 mock
                if (item.type === 'mock_driver') {
                  const d = item.data as HistoryItem;
                  return (
                    <Card key={`driver-${d.id}`} size="small" style={{ marginBottom: 8 }}>
                      <Space>
                        <Tag color="green" icon={<AimOutlined />}>车主手势</Tag>
                        <Tag style={{ fontSize: 14 }}>{d.result.gesture as string}</Tag>
                        <span style={{ color: '#8c8c8c' }}>{dayjs(d.createdAt).format('YYYY-MM-DD HH:mm:ss')}</span>
                      </Space>
                    </Card>
                  );
                }
                // 交警手势单条 (图片/摄像头)
                if (item.type === 'single') {
                  const d = item.data as HistoryItem;
                  return (
                    <Card key={`single-${d.id}`} size="small" style={{ marginBottom: 8 }}>
                      <Space>
                        <Tag color="purple" icon={<HighlightOutlined />}>交警手势</Tag>
                        <Tag color={d.recognitionType === 'camera_stream' ? 'cyan' : 'blue'}>
                          {d.recognitionType === 'image' ? '图片' : '摄像头'}
                        </Tag>
                        <Tag style={{ fontSize: 14 }}>{d.gesture} {(d.confidence! * 100).toFixed(0)}%</Tag>
                        {d.success === false && <Tag color="red">失败</Tag>}
                        <span style={{ color: '#8c8c8c' }}>{dayjs(d.createdAt).format('YYYY-MM-DD HH:mm:ss')}</span>
                      </Space>
                    </Card>
                  );
                }
                // 视频分组
                if (item.type === 'video_group') {
                  const g = item.data as VideoGroup;
                  return (
                    <Card
                      key={`video-${g.videoSessionId}`}
                      size="small"
                      style={{ marginBottom: 12 }}
                      title={
                        <Space>
                          <VideoCameraOutlined />
                          <span>{g.filename}</span>
                          <Tag color="orange">视频</Tag>
                        </Space>
                      }
                      extra={
                        <span style={{ color: '#8c8c8c', fontSize: 12 }}>
                          {dayjs(g.createdAt).format('YYYY-MM-DD HH:mm:ss')}
                          {g.videoDuration != null && ` · ${g.videoDuration.toFixed(1)}s`}
                          {g.framesProcessed != null && ` · ${g.framesProcessed}帧`}
                          {g.inferenceMs != null && ` · ${g.inferenceMs.toFixed(0)}ms`}
                        </span>
                      }
                    >
                      {/* 视频动作时间线 */}
                      <div style={{ position: 'relative', height: 32, background: '#f5f5f5', borderRadius: 6, overflow: 'hidden', marginBottom: 10 }}>
                        {g.segments.map((seg, i) => {
                          const totalDuration = g.videoDuration || (g.segments.length > 0 ? g.segments[g.segments.length - 1].segments?.[0]?.end ?? 1 : 1);
                          const left = totalDuration > 0 ? ((seg.segments?.[0]?.start ?? 0) / totalDuration) * 100 : 0;
                          const segEnd = seg.segments?.[0]?.end ?? 0;
                          const segStart = seg.segments?.[0]?.start ?? 0;
                          const width = totalDuration > 0 ? Math.max(((segEnd - segStart) / totalDuration) * 100, 1) : 1;
                          return (
                            <div
                              key={i}
                              title={`${segStart.toFixed(1)}s-${segEnd.toFixed(1)}s: ${seg.gesture}`}
                              style={{
                                position: 'absolute', left: `${left}%`, width: `${width}%`,
                                height: '100%', borderRight: '2px solid #fff',
                                background: GESTURE_COLORS[seg.gestureId ?? 0] || '#8c8c8c',
                              }}
                            />
                          );
                        })}
                      </div>
                      {/* 手势段列表 */}
                      <Space wrap>
                        {g.segments.map((seg, i) => (
                          <Tag key={i} color={GESTURE_COLORS[seg.gestureId ?? 0] || 'default'}>
                            {seg.gesture} {(seg.confidence! * 100).toFixed(0)}%
                            {seg.segments?.[0] ? ` ${seg.segments[0].start.toFixed(1)}s-${seg.segments[0].end.toFixed(1)}s` : ''}
                          </Tag>
                        ))}
                      </Space>
                    </Card>
                  );
                }
                return null;
              })}
            </div>
          ) : (
            <Empty description={loading ? '加载中...' : '暂无历史记录'} />
          )}
        </Spin>
      </Card>
    </div>
  );
};

export default History;
