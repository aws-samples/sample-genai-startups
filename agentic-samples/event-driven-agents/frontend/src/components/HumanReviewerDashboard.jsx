import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { useToast } from '@/hooks/use-toast';
import { Toaster } from '@/components/ui/toaster';
import { useAppSyncEvents } from '@/hooks/useAppSyncEvents';
import { 
  CheckCircle, 
  XCircle, 
  Clock, 
  Download,
  FileText, 
  MessageSquare,
  Wifi,
  WifiOff,
  Loader2,
  Calendar,
  Hash,
  RefreshCw,
  ArrowLeft,
  Search
} from 'lucide-react';

const HumanReviewerDashboard = () => {
  const [reviewRequests, setReviewRequests] = useState([]);
  const [comments, setComments] = useState({});
  const [submittingReviews, setSubmittingReviews] = useState(new Set());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const { toast } = useToast();
  const navigate = useNavigate();

  // Handle incoming AppSync Events messages
  const handleAppSyncMessage = useCallback((eventData) => {
    console.log('Received AppSync event:', eventData);
    
    // AppSync events now contain the review request directly
    if (eventData.id && eventData.decision === 'pending') {
      setReviewRequests(prev => {
        const exists = prev.some(req => req.id === eventData.id);
        if (!exists) {
          toast({
            title: "New Review Request",
            description: "New review request received",
          });
          return [eventData, ...prev];
        }
        return prev;
      });
    }
  }, [toast]); // toast is stable from the hook

  // Human Reviewer AppSync Events configuration (memoized to prevent reconnections)
  const humanReviewerConfig = useMemo(() => ({
    realtimeDomain: import.meta.env.VITE_HUMAN_REVIEWER_REALTIME_DOMAIN,
    httpDomain: import.meta.env.VITE_HUMAN_REVIEWER_HTTP_DOMAIN,
    apiKey: import.meta.env.VITE_HUMAN_REVIEWER_API_KEY,
    channel: '/human-reviewer/requests'
  }), []);

  // Use the AppSync Events hook
  const { isConnected, connectionStatus } = useAppSyncEvents(handleAppSyncMessage, humanReviewerConfig);

  useEffect(() => {
    // Fetch real review requests from the API
    fetchReviewRequests();
  }, []);

  const fetchReviewRequests = async () => {
    try {
      const apiUrl = import.meta.env.VITE_HUMAN_REVIEW_API_URL;
      
      if (!apiUrl) {
        console.warn('API Gateway URL not configured. Using sample data only.');
        // Keep sample data as fallback
        const sampleRequests = [
          {
            id: 'uuid-12345678-1234-1234-1234-123456789012',
            query: 'What are the key findings and recommendations from this research report? Please review the analysis and provide expert feedback.',
            summary: 'This research document contains comprehensive analysis including data findings, expert recommendations, and actionable insights. The report includes market research showing emerging trends and recommendations for strategic planning.',
            s3uri: 's3://documents-bucket/research-report.pdf',
            decision: 'pending',
            createdAt: new Date().toISOString(),
          }
        ];
        setReviewRequests(sampleRequests);
        return;
      }

      const response = await fetch(`${apiUrl}/reviews`);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      console.log('Fetched review requests:', data);
      
      // Backend now returns reviews directly, not wrapped in {reviews: [...]}
      setReviewRequests(Array.isArray(data) ? data : []);
      
    } catch (error) {
      console.error('Error fetching review requests:', error);
      toast({
        title: "Error",
        description: `Failed to fetch reviews: ${error.message}`,
        variant: "destructive",
      });
    }
  };

  const handleCommentChange = (id, comment) => {
    setComments(prev => ({
      ...prev,
      [id]: comment
    }));
  };

  const handleReviewDecision = async (id, decision) => {
    try {
      const comment = comments[id] || '';
      
      // Add to submitting set to show loading state
      setSubmittingReviews(prev => new Set([...prev, id]));
      
      // Get API Gateway URL from environment variables
      const apiUrl = import.meta.env.VITE_HUMAN_REVIEW_API_URL;
      
      if (!apiUrl) {
        throw new Error('API Gateway URL not configured. Please check VITE_HUMAN_REVIEW_API_URL environment variable.');
      }
      
      // Call the API Gateway endpoint
      const response = await fetch(`${apiUrl}/reviews`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          invocationId: id,
          decision: decision,
          comments: comment || undefined
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      console.log('Review submitted successfully:', result);

      // Remove from submitting set
      setSubmittingReviews(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });

      // Remove the item from the list (since it's no longer pending)
      setReviewRequests(prev => 
        prev.filter(request => request.id !== id)
      );

      // Clear the comment for this request
      setComments(prev => {
        const newComments = { ...prev };
        delete newComments[id];
        return newComments;
      });

      // Show success toast
      toast({
        title: "Success",
        description: `Review ${decision === 'approved' ? 'approved' : 'rejected'} and sent successfully!`,
      });
      
    } catch (error) {
      console.error('Error submitting review decision:', error);
      
      // Remove from submitting set
      setSubmittingReviews(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });
      
      // Show error toast
      toast({
        title: "Error",
        description: `Failed to submit review: ${error.message}`,
        variant: "destructive",
      });
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await fetchReviewRequests();
      toast({
        title: "Success",
        description: "Review requests refreshed successfully",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to refresh review requests",
        variant: "destructive",
      });
    } finally {
      setIsRefreshing(false);
    }
  };

  const downloadPDF = (presignedUrl, fileName) => {
    window.open(presignedUrl, '_blank');
  };


  const pendingRequests = reviewRequests.filter(request => request.decision === 'pending');

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top Navigation Bar */}
      <div className="w-full bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/user')}
              className="flex items-center space-x-2"
            >
              <ArrowLeft className="h-4 w-4" />
              <span>Back to User Portal</span>
            </Button>
            <div className="h-6 w-px bg-gray-300"></div>
            <div className="flex items-center space-x-2">
              <Search className="h-6 w-6 text-blue-600" />
              <span className="font-semibold text-gray-900">Research AI - Reviewer Portal</span>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {isConnected ? (
              <Wifi className="h-4 w-4 text-green-600" />
            ) : (
              <WifiOff className="h-4 w-4 text-red-600" />
            )}
            <Badge variant={isConnected ? "default" : "destructive"} className="flex items-center space-x-1">
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'} animate-pulse`} />
              <span>{connectionStatus}</span>
            </Badge>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-3xl font-bold tracking-tight">Human Reviewer Dashboard</h1>
            <p className="text-muted-foreground">
              Review and approve document analysis requests
            </p>
          </div>
        </div>
      </div>
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <FileText className="h-5 w-5" />
            <h2 className="text-xl font-semibold">
              Pending Reviews
            </h2>
            <Badge variant="outline" className="ml-2">
              {pendingRequests.length}
            </Badge>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center space-x-2"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </Button>
        </div>

        {/* Review Requests */}
        <div className="space-y-4">
          {pendingRequests.length === 0 ? (
            <Card className="p-12">
              <div className="text-center space-y-4">
                <div className="mx-auto w-12 h-12 bg-muted rounded-full flex items-center justify-center">
                  <FileText className="h-6 w-6 text-muted-foreground" />
                </div>
                <div className="space-y-2">
                  <h3 className="text-lg font-medium">No Review Requests</h3>
                  <p className="text-muted-foreground">
                    There are currently no pending review requests.
                  </p>
                </div>
              </div>
            </Card>
          ) : (
            <Accordion type="single" collapsible className="space-y-4">
              {pendingRequests.map((request) => (
                <AccordionItem 
                  key={request.id} 
                  value={request.id}
                  className="border rounded-lg bg-card"
                >
                  <AccordionTrigger className="px-6 py-4 hover:no-underline">
                    <div className="flex-1 text-left space-y-3 pr-4">
                      {/* ID Row */}
                      <div className="flex items-center space-x-3">
                        <Badge variant="default" className="flex items-center space-x-1">
                          <Clock className="h-3 w-3" />
                          <span>PENDING</span>
                        </Badge>
                        <div className="flex items-center space-x-1 text-xs text-muted-foreground">
                          <Hash className="h-3 w-3" />
                          <span className="font-mono">
                            {request.id.substring(0, 8)}...
                          </span>
                        </div>
                      </div>
                      
                      {/* Query Preview */}
                      <div>
                        <h3 className="text-base font-semibold leading-relaxed">
                          {request.query.length > 120 
                            ? `${request.query.substring(0, 120)}...` 
                            : request.query}
                        </h3>
                      </div>
                      
                      {/* Summary Preview */}
                      <p className="text-sm text-muted-foreground line-clamp-2">
                        {request.summary.length > 150 
                          ? `${request.summary.substring(0, 150)}...` 
                          : request.summary}
                      </p>
                      
                      {/* Metadata */}
                      <div className="flex items-center space-x-4 text-xs text-muted-foreground">
                        <div className="flex items-center space-x-1">
                          <Calendar className="h-3 w-3" />
                          <span>{new Date(request.createdAt).toLocaleString()}</span>
                        </div>
                      </div>
                    </div>
                  </AccordionTrigger>
                    
                    <AccordionContent className="px-6 pb-6">
                      <div className="space-y-6">
                        <Separator />
                        
                        {/* Full Request Details */}
                        <div className="space-y-4">
                          <div>
                            <h4 className="font-medium mb-2 flex items-center space-x-2">
                              <MessageSquare className="h-4 w-4" />
                              <span>Original Request</span>
                            </h4>
                            <div className="bg-muted p-4 rounded-md text-sm">
                              {request.query}
                            </div>
                          </div>

                          <div>
                            <h4 className="font-medium mb-2 flex items-center space-x-2">
                              <FileText className="h-4 w-4" />
                              <span>Document Summary</span>
                            </h4>
                            <div className="bg-muted p-4 rounded-md text-sm">
                              {request.summary}
                            </div>
                          </div>

                          {/* Document Download */}
                          {request.s3uri && (
                            <div>
                              <h4 className="font-medium mb-2">Document</h4>
                              <Button
                                variant="outline"
                                onClick={() => downloadPDF(request.presignedUrl, `document-${request.id.substring(0, 8)}.pdf`)}
                                className="flex items-center space-x-2"
                                disabled={!request.presignedUrl}
                              >
                                <Download className="h-4 w-4" />
                                <span>Download PDF</span>
                              </Button>
                            </div>
                          )}

                          {/* Comments */}
                          <div>
                            <h4 className="font-medium mb-2">Comments</h4>
                            <Textarea
                              value={comments[request.id] || ''}
                              onChange={(e) => handleCommentChange(request.id, e.target.value)}
                              placeholder="Add your review comments here..."
                              rows={3}
                              className="resize-none"
                            />
                          </div>

                          {/* Action Buttons */}
                          <div className="flex space-x-3 pt-4">
                            <Button
                              onClick={() => handleReviewDecision(request.id, 'approved')}
                              disabled={submittingReviews.has(request.id)}
                              className="flex-1"
                              size="lg"
                            >
                              {submittingReviews.has(request.id) ? (
                                <>
                                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                  Submitting...
                                </>
                              ) : (
                                <>
                                  <CheckCircle className="mr-2 h-4 w-4" />
                                  Approve
                                </>
                              )}
                            </Button>
                            <Button
                              variant="destructive"
                              onClick={() => handleReviewDecision(request.id, 'rejected')}
                              disabled={submittingReviews.has(request.id)}
                              className="flex-1"
                              size="lg"
                            >
                              {submittingReviews.has(request.id) ? (
                                <>
                                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                  Submitting...
                                </>
                              ) : (
                                <>
                                  <XCircle className="mr-2 h-4 w-4" />
                                  Reject
                                </>
                              )}
                            </Button>
                          </div>
                        </div>
                      </div>
                    </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          )}
        </div>

        <Toaster />
      </div>
    </div>
  );
};

export default HumanReviewerDashboard;
