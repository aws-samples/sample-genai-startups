import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useToast } from '@/hooks/use-toast';
import { useAppSyncEvents } from '@/hooks/useAppSyncEvents';
import { Toaster } from '@/components/ui/toaster';
import Timeline from '@/components/Timeline';
import {
  Search,
  FileText,
  Clock,
  CheckCircle,
  AlertCircle,
  Loader2,
  Activity,
  Brain,
  Shield,
  User,
  UserCheck,
  Download,
  Hash,
  Wifi
} from 'lucide-react';

const UserDashboard = () => {
  const [query, setQuery] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [analysisHistory, setAnalysisHistory] = useState([]);
  const [toolEvents, setToolEvents] = useState([]);
  const { toast } = useToast();
  const navigate = useNavigate();

  // Generate persistent invocation ID that stays the same until page reload
  const [invocationId] = useState(() => crypto.randomUUID());

  // Store current query in a ref to avoid callback dependency
  const queryRef = useRef(query);
  useEffect(() => {
    queryRef.current = query;
  }, [query]);

  // Handle incoming AppSync events for user responses and tool status
  const handleAppSyncMessage = useCallback((eventData) => {
    console.log('Received AppSync event:', eventData);
    
    // Check agentInvocationId for tool status events, invocationId for final results
    const isRelevantEvent = eventData.type === 'toolStatus' 
      ? eventData.agentInvocationId === invocationId 
      : eventData.invocationId === invocationId;
    
    if (isRelevantEvent) {
      // Handle tool status updates
      if (eventData.type === 'toolStatus') {
        const executionId = eventData.invocationId; // Use tool invocation ID as execution ID
        
        setToolEvents(prev => {
          let newEvents = [...prev];
          
          if (eventData.status === 'invoked') {
            // Mark the current "AI Researcher Thinking" as complete if it exists
            newEvents = newEvents.map(event => 
              event.toolName === 'thinking' && event.status === 'in_progress'
                ? { ...event, status: 'completed' }
                : event
            );
            
            // Add the new tool invocation (only if not already present)
            const existingIndex = newEvents.findIndex(event => event.executionId === executionId);
            if (existingIndex === -1) {
              newEvents.push({
                id: executionId,
                executionId: executionId,
                toolName: eventData.toolName,
                status: 'in_progress',
                message: eventData.message,
                timestamp: eventData.timestamp
              });
            }
          } else if (eventData.status === 'executed') {
            // Mark the tool as completed
            newEvents = newEvents.map(event => 
              event.executionId === executionId
                ? { ...event, status: 'completed' }
                : event
            );
            
            // Add new "AI Researcher Thinking" in progress
            const newThinking = {
              id: `thinking-${Date.now()}`,
              toolName: 'thinking',
              status: 'in_progress',
              message: 'AI Researcher Thinking',
              timestamp: eventData.timestamp
            };
            
            // Only add if the last event is not the same thinking entry
            const lastEvent = newEvents[newEvents.length - 1];
            if (!lastEvent || 
                lastEvent.toolName !== 'thinking' || 
                lastEvent.status !== 'in_progress' ||
                lastEvent.message !== 'AI Researcher Thinking') {
              newEvents.push(newThinking);
            }
          }
          
          // Keep only last 20 events to prevent memory issues
          return newEvents.slice(-20);
        });
        return;
      }
      
      // Handle final analysis result
      if (eventData.summary) {
        setIsAnalyzing(false);
        
        // Mark the final thinking state as completed
        setToolEvents(prev => 
          prev.map(event => 
            event.toolName === 'thinking' && event.status === 'in_progress'
              ? { ...event, status: 'completed' }
              : event
          )
        );
        
        const result = {
          id: eventData.invocationId,
          query: queryRef.current, // Use ref to get current query without dependency
          timestamp: new Date(eventData.timestamp),
          summary: eventData.summary,
          s3Uri: eventData.s3Uri,
          presignedUrl: eventData.presignedUrl,
          disclaimer: "This analysis is for informational purposes only and should not replace professional advice. Please consult with relevant experts for proper guidance and recommendations."
        };
        
        setAnalysisResult(result);
        setAnalysisHistory(prev => [result, ...prev.slice(0, 4)]);
        
        toast({
          title: "Analysis Complete",
          description: "Your research report is ready for review.",
        });
      }
    }
  }, [invocationId, toast]); // Stable dependencies only

  // User Interface AppSync Events configuration (memoized to prevent reconnections)
  const userConfig = useMemo(() => ({
    realtimeDomain: import.meta.env.VITE_USER_REALTIME_DOMAIN,
    httpDomain: import.meta.env.VITE_USER_HTTP_DOMAIN,
    apiKey: import.meta.env.VITE_USER_API_KEY,
    channel: `/agent/${invocationId}`
  }), [invocationId]);

  // Use the AppSync Events hook with persistent invocation ID
  const { isConnected, connectionStatus } = useAppSyncEvents(
    handleAppSyncMessage, 
    userConfig
  );

  const handleQuerySubmission = async () => {
    if (!query.trim()) {
      toast({
        title: "Please enter your research query",
        description: "Enter your research topic in the text area above to get started.",
        variant: "destructive",
      });
      return;
    }

    setIsAnalyzing(true);
    setAnalysisResult(null);
    setToolEvents([{
      id: 'thinking',
      toolName: 'thinking',
      status: 'in_progress',
      message: 'AI Researcher Thinking',
      timestamp: new Date().toISOString()
    }]);

    toast({
      title: "Analysis Started",
      description: "Our research AI is analyzing your query...",
    });

    try {
      // Submit query to user interface API
      const apiUrl = import.meta.env.VITE_USER_API_URL;
      const response = await fetch(`${apiUrl}/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: query,
          invocationId: invocationId
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      console.log('Query submission response:', data);
      
      // Clear the query input after successful submission
      setQuery('');
      
      toast({
        title: "Request Submitted",
        description: "Your research query has been submitted for analysis. Please wait for the AI response...",
      });

    } catch (error) {
      console.error('Error submitting query:', error);
      setIsAnalyzing(false);
      
      toast({
        title: "Submission Failed",
        description: `Failed to submit query: ${error.message}`,
        variant: "destructive",
      });
    }
  };


  return (
    <div className="min-h-screen w-full bg-gradient-to-br from-blue-50 to-white flex flex-col">
      {/* Top Navigation Bar */}
      <div className="w-full bg-white shadow-sm border-b">
        <div className="w-full px-4 py-3 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Search className="h-6 w-6 text-blue-600" />
            <span className="font-semibold text-gray-900">Research AI</span>
          </div>
          <div className="flex items-center space-x-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/reviewer')}
              className="flex items-center space-x-2"
            >
              <UserCheck className="h-4 w-4" />
              <span>Reviewer Dashboard</span>
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-1 w-full px-4 py-8 flex flex-col">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center mb-4">
            <div className="bg-blue-100 p-3 rounded-full mr-4">
              <Search className="h-8 w-8 text-blue-600" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Deep Research Agent</h1>
              <p className="text-lg text-gray-600 mt-1">
                AI-powered comprehensive research and analysis
              </p>
            </div>
          </div>
          
          <div className="flex items-center justify-center space-x-6 text-sm text-gray-500">
            <div className="flex items-center space-x-1">
              <Shield className="h-4 w-4" />
              <span>Secure & Private</span>
            </div>
            <div className="flex items-center space-x-1">
              <Brain className="h-4 w-4" />
              <span>AI-Powered</span>
            </div>
            <div className="flex items-center space-x-1">
              <Activity className="h-4 w-4" />
              <span>24/7 Available</span>
            </div>
          </div>
        </div>

        {/* Main Content - Centered and Full Width */}
        <div className="flex-1 flex flex-col justify-center w-full max-w-4xl mx-auto">
          {/* Main Query Input Card - Centered - Hidden when analyzing */}
          {!isAnalyzing && (
            <Card className="mb-8 shadow-lg border-0 w-full">
            <CardHeader className="bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-t-lg">
              <CardTitle className="flex items-center justify-center space-x-2 text-xl">
                <User className="h-6 w-6" />
                <span>Enter Your Research Query</span>
              </CardTitle>
              <CardDescription className="text-blue-100 text-center">
                Please provide a detailed description of the topic you'd like to research. 
                Be specific about what aspects you're most interested in learning about.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-8">
              <div className="space-y-6">
                <div className="flex justify-center">
                  <div className="w-full">
                    <Textarea
                      placeholder="Example: I want to understand the latest developments in renewable energy storage technologies, particularly focusing on battery innovations, their environmental impact, and commercial viability. Please include recent research findings, market trends, and expert opinions on the future of energy storage..."
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      rows={12}
                      className="text-base leading-relaxed resize-none w-full"
                      disabled={isAnalyzing}
                    />
                  </div>
                </div>
                
                <div className="flex items-center justify-between">
                  <div className="text-sm text-gray-500">
                    {query.length}/2000 characters
                  </div>
                  <Button 
                    onClick={handleQuerySubmission}
                    disabled={isAnalyzing || !query.trim()}
                    size="lg"
                    className="bg-blue-600 hover:bg-blue-700 px-8 py-3"
                  >
                    {isAnalyzing ? (
                      <>
                        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                        Researching...
                      </>
                    ) : (
                      <>
                        <Activity className="mr-2 h-5 w-5" />
                        Start Research
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
          )}

          {/* Analysis Progress */}
          {isAnalyzing && (
            <Card className="mb-8 border-blue-200 w-full">
              <CardHeader>
                <CardTitle className="flex items-center justify-center space-x-2 text-blue-700">
                  <Brain className="h-5 w-5" />
                  <span>AI Analysis in Progress</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3 text-center">
                  <Loader2 className="h-8 w-8 animate-spin mx-auto text-blue-600" />
                  <div className="text-sm text-gray-600">
                    Processing your research query and generating comprehensive report...
                  </div>
                  <div className="text-xs text-gray-500">
                    Request ID: {invocationId}
                  </div>
                  <div className="flex items-center justify-center space-x-1 text-xs">
                    {isConnected ? (
                      <>
                        <Wifi className="h-3 w-3 text-green-600" />
                        <span className="text-green-600">Connected for real-time updates</span>
                      </>
                    ) : (
                      <>
                        <Wifi className="h-3 w-3 text-gray-400" />
                        <span className="text-gray-500">Status: {connectionStatus}</span>
                      </>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Timeline */}
          <Timeline events={toolEvents} isAnalyzing={isAnalyzing} />
        </div>

        {/* Analysis Result */}
        {analysisResult && (
          <Card className="mb-8 shadow-lg border-green-200 w-full">
            <CardHeader className="bg-gradient-to-r from-green-50 to-green-100 border-b border-green-200">
              <CardTitle className="flex items-center justify-center space-x-2 text-green-800">
                <CheckCircle className="h-6 w-6" />
                <span>Research Report Generated</span>
              </CardTitle>
              <CardDescription className="text-green-700 text-center">
                Generated on {analysisResult.timestamp.toLocaleString()}
              </CardDescription>
            </CardHeader>
            <CardContent className="p-6 space-y-6">
              {/* Research Report Summary */}
              <div>
                <h3 className="font-semibold text-lg mb-3 flex items-center justify-center space-x-2">
                  <FileText className="h-5 w-5" />
                  <span>Research Report Summary</span>
                </h3>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                    {analysisResult.summary}
                  </p>
                </div>
              </div>

              {/* Download Report */}
              {analysisResult.presignedUrl && (
                <div className="text-center">
                  <h3 className="font-semibold text-lg mb-3 flex items-center justify-center space-x-2">
                    <Download className="h-5 w-5" />
                    <span>Download Full Report</span>
                  </h3>
                  <Button
                    onClick={() => window.open(analysisResult.presignedUrl, '_blank')}
                    className="bg-blue-600 hover:bg-blue-700"
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Download PDF Report
                  </Button>
                  <p className="text-xs text-gray-500 mt-2">
                    PDF report link expires in 24 hours
                  </p>
                </div>
              )}

              {/* Request Details */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-start space-x-2">
                  <Hash className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <h4 className="font-medium text-blue-800 mb-1">Request Details</h4>
                    <p className="text-sm text-blue-700">Request ID: {analysisResult.id}</p>
                    {analysisResult.s3Uri && (
                      <p className="text-xs text-blue-600 mt-1">Report stored: {analysisResult.s3Uri}</p>
                    )}
                  </div>
                </div>
              </div>

              {/* Disclaimer */}
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <div className="flex items-start space-x-2">
                  <AlertCircle className="h-5 w-5 text-yellow-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <h4 className="font-medium text-yellow-800 mb-1">Important Disclaimer</h4>
                    <p className="text-sm text-yellow-700">{analysisResult.disclaimer}</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Analysis History */}
        {analysisHistory.length > 0 && (
          <Card className="shadow-lg w-full">
            <CardHeader>
              <CardTitle className="flex items-center justify-center space-x-2">
                <Clock className="h-5 w-5" />
                <span>Recent Research Reports</span>
              </CardTitle>
              <CardDescription className="text-center">
                Your previous research analyses
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {analysisHistory.map((analysis) => (
                  <div key={analysis.id} className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 transition-colors">
                    <div className="flex-1">
                      <p className="text-sm text-gray-600 truncate max-w-md">
                        {analysis.query.substring(0, 100)}...
                      </p>
                      <div className="flex items-center space-x-2 mt-1">
                        <Badge variant="outline" className="text-xs">
                          Report Generated
                        </Badge>
                        <span className="text-xs text-gray-500">
                          {analysis.timestamp.toLocaleDateString()}
                        </span>
                        {analysis.presignedUrl && (
                          <Badge variant="secondary" className="text-xs">
                            PDF Available
                          </Badge>
                        )}
                      </div>
                    </div>
                    <div className="flex space-x-2">
                      {analysis.presignedUrl && (
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => window.open(analysis.presignedUrl, '_blank')}
                        >
                          <Download className="h-3 w-3 mr-1" />
                          PDF
                        </Button>
                      )}
                      <Button variant="outline" size="sm">
                        View Details
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        <Toaster />
      </div>
    </div>
  );
};

export default UserDashboard;
