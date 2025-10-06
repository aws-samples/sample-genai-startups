import { useState, useEffect, useRef, useMemo } from 'react';

interface AppSyncConfig {
  realtimeDomain: string;
  httpDomain: string;
  apiKey: string;
  channel: string;
}

interface AppSyncEventData {
  [key: string]: any;
}

/**
 * AppSync Events WebSocket hook - fixed for single connection per component
 * https://aws.amazon.com/blogs/mobile/announcing-aws-appsync-events/
 */
export function useAppSyncEvents(
  onMessage: (eventData: AppSyncEventData) => void,
  config: AppSyncConfig | null
) {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [connectionStatus, setConnectionStatus] = useState<string>('Disconnected');
  const socketRef = useRef<WebSocket | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const onMessageRef = useRef<(eventData: AppSyncEventData) => void>(onMessage);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Keep onMessage ref updated without triggering reconnections
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  // Memoize config to prevent unnecessary reconnections
  const configKey = useMemo(() => {
    if (!config) return null;
    return JSON.stringify({
      realtimeDomain: config.realtimeDomain,
      httpDomain: config.httpDomain,
      apiKey: config.apiKey,
      channel: config.channel
    });
  }, [config]);

  useEffect(() => {
    // Track component mount status
    isMountedRef.current = true;

    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    // Clear any existing reconnection timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Close existing connection if any
    if (socketRef.current) {
      console.log('Closing existing WebSocket connection for new config');
      socketRef.current.close();
      socketRef.current = null;
    }

    if (!config || !configKey) {
      setIsConnected(false);
      setConnectionStatus('Not configured');
      return;
    }

    const REALTIME_DOMAIN = config.realtimeDomain;
    const HTTP_DOMAIN = config.httpDomain;
    const API_KEY = config.apiKey;
    const CHANNEL = config.channel;

    if (!REALTIME_DOMAIN || !HTTP_DOMAIN || !API_KEY || !CHANNEL) {
      console.warn('AppSync Events API configuration not found', { REALTIME_DOMAIN, HTTP_DOMAIN, API_KEY, CHANNEL });
      setConnectionStatus('Configuration Missing');
      return;
    }

    const authorization = { 'x-api-key': API_KEY, host: HTTP_DOMAIN };

    function getAuthProtocol(): string {
      const header = btoa(JSON.stringify(authorization))
        .replace(/\+/g, '-') // Convert '+' to '-'
        .replace(/\//g, '_') // Convert '/' to '_'
        .replace(/=+$/, '') // Remove padding `=`
      return `header-${header}`;
    }

    const connect = async (): Promise<void> => {
      // Prevent connection if component is unmounted or connection already exists
      if (!isMountedRef.current || socketRef.current) {
        return;
      }

      try {
        setConnectionStatus('Connecting...');
        console.log('Connecting to AppSync Events WebSocket:', `wss://${REALTIME_DOMAIN}/event/realtime`);

        const socket = new WebSocket(
          `wss://${REALTIME_DOMAIN}/event/realtime`,
          ['aws-appsync-event-ws', getAuthProtocol()]
        );

        socket.onopen = () => {
          if (!isMountedRef.current) {
            socket.close();
            return;
          }
          
          console.log('WebSocket connected to AppSync Events');
          socketRef.current = socket;
          setIsConnected(true);
          setConnectionStatus('Connected');
          socket.send(JSON.stringify({ type: 'connection_init' }));
        };

        socket.onclose = (evt) => {
          console.log('WebSocket connection closed:', evt.code, evt.reason);
          
          if (socketRef.current === socket) {
            socketRef.current = null;
            setIsConnected(false);
            setConnectionStatus('Disconnected');
          }
          
          // Only auto-reconnect if component is still mounted and closure wasn't intentional
          if (isMountedRef.current && evt.code !== 1000) {
            console.log('Scheduling reconnection in 5 seconds...');
            reconnectTimeoutRef.current = setTimeout(() => {
              if (isMountedRef.current) {
                connect();
              }
            }, 5000);
          }
        };

        socket.onerror = (error) => {
          console.error('WebSocket error:', error);
          
          if (socketRef.current === socket) {
            setIsConnected(false);
            setConnectionStatus('Error');
          }
        };

        socket.onmessage = (event) => {
          if (!isMountedRef.current) return;
          
          try {
            const message = JSON.parse(event.data);
            console.log('Received WebSocket message:', message);

            if (message.type === 'connection_ack') {
              console.log('Connection acknowledged, subscribing to channel...');
              socket.send(JSON.stringify({
                type: 'subscribe',
                id: crypto.randomUUID(),
                channel: CHANNEL,
                authorization
              }));
              console.log(`Subscribed to ${CHANNEL} channel`);
            } else if (message.type === 'data' && message.event) {
              try {
                const eventData = typeof message.event === 'string' 
                  ? JSON.parse(message.event) 
                  : message.event;
                
                console.log('Received event data:', eventData);
                if (onMessageRef.current) {
                  onMessageRef.current(eventData);
                }
              } catch (parseError) {
                console.error('Error parsing event data:', parseError);
                if (onMessageRef.current) {
                  onMessageRef.current(message.event);
                }
              }
            } else if (message.type === 'error') {
              console.error('WebSocket subscription error:', message);
            }
          } catch (error) {
            console.error('Error parsing WebSocket message:', error);
          }
        };

      } catch (error) {
        console.error('Failed to connect to AppSync Events:', error);
        setConnectionStatus('Failed');
        
        // Only retry if component is still mounted
        if (isMountedRef.current) {
          console.log('Scheduling retry in 10 seconds...');
          reconnectTimeoutRef.current = setTimeout(() => {
            if (isMountedRef.current) {
              connect();
            }
          }, 10000);
        }
      }
    };

    connect();

    // Cleanup on unmount or config change
    return () => {
      console.log('Cleaning up WebSocket connection');
      
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      
      setIsConnected(false);
      setConnectionStatus('Disconnected');
    };
  }, [configKey]); // Only depend on config changes, not onMessage

  return {
    isConnected,
    connectionStatus
  };
}
