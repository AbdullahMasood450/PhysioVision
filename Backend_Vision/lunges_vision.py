import cv2
import mediapipe as mp
import numpy as np
from collections import defaultdict
import logging
import base64
# import asyncio

logger = logging.getLogger(__name__)
class LungesAnalyzer:
    def __init__(self):
        # Initialize MediaPipe Pose
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Initialize model components
        self.scaler = None
        self.pca = None
        self.model = None
        self.is_trained = False
        
        # Define the landmarks we're interested in (hip, knee, ankle only)
        self.target_landmarks = [
            'LEFT_HIP', 'LEFT_KNEE', 'LEFT_ANKLE',
            'RIGHT_HIP', 'RIGHT_KNEE', 'RIGHT_ANKLE'
        ]
        
    def extract_keypoints(self, frame):
        """Extract hip, knee, and ankle keypoints from a single frame."""
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process the frame
        results = self.pose.process(frame_rgb)
        
        if not results.pose_landmarks:
            return None, None
        
        # Extract only hip, knee, ankle keypoints
        keypoints = []
        landmark_dict = {}
        
        for i, landmark in enumerate(results.pose_landmarks.landmark):
            name = self.mp_pose.PoseLandmark(i).name
            if name in self.target_landmarks:
                landmark_dict[name] = [landmark.x, landmark.y, landmark.z]
        
        # Determine leading leg
        knee_r = landmark_dict['RIGHT_KNEE'][:2]  # Just x,y for position comparison
        knee_l = landmark_dict['LEFT_KNEE'][:2]
        
        # Lower y-value means higher in the image (closer to top of frame)
        if knee_r[1] < knee_l[1]:  # Right knee is higher in the frame
            leading_leg = "Right"  # Right leg is forward
        else:
            leading_leg = "Left"  # Left leg is forward
            
        # Extract features in a consistent order
        for name in self.target_landmarks:
            keypoints.extend(landmark_dict[name])
            
        return np.array(keypoints), leading_leg
    
    def normalize_side(self, keypoints, leading_leg):
        """
        Normalize left/right sides to treat them as the same movement pattern.
        This maps all lunges to a standardized form regardless of which leg is forward.
        """
        # Reshape keypoints to have landmarks as rows with [x,y,z] columns
        # We have 6 landmarks (L/R hip, knee, ankle) with 3 coordinates each
        landmarks = keypoints.reshape(6, 3)
        
        # Standardize to always have the same leg configuration
        # If right leg is forward but we want left leg to be our standard (or vice versa)
        if leading_leg == "Right":
            # Swap left and right sides
            temp = np.copy(landmarks[0:3])
            landmarks[0:3] = landmarks[3:6]
            landmarks[3:6] = temp
        
        # Return flattened normalized keypoints
        return landmarks.flatten()
    
    def calculate_lunge_features(self, keypoints, original_leading_leg):
        """Calculate important angles and distances for lunge form assessment."""
        # Reshape keypoints to have landmarks as rows with [x,y,z] columns
        landmarks = keypoints.reshape(6, 3)
        
        # Extract individual landmarks
        front_hip = landmarks[0]    # Using left as front leg (after normalization)
        front_knee = landmarks[1]
        front_ankle = landmarks[2]
        
        # Calculate angle between three points
        def calculate_angle(a, b, c):
            a = np.array(a)
            b = np.array(b)
            c = np.array(c)
            
            ba = a - b
            bc = c - b
            
            cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
            # Clip to avoid numerical errors
            cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
            angle = np.arccos(cosine_angle)
            return np.degrees(angle)
        
        # Calculate relevant angles and distances
        features = {}
        
        # Front leg angles
        features['front_knee_angle'] = calculate_angle(front_hip, front_knee, front_ankle)
        
        # Store the original leading leg for reference
        features['leading_leg'] = original_leading_leg
        
        return features
    
    def load_model(self, model_path):
        try:
            print("Attempting to load model...")
            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)
                self.scaler = model_data['scaler']
                self.pca = model_data['pca']
                self.model = model_data['model']
                self.feature_means = model_data['feature_means']
                self.feature_stds = model_data['feature_stds']
            self.is_trained = True
            print("Model loaded successfully!")
        except Exception as e:
            print(f"Error loading model: {e}")



    def reset_counters(self):
        """Reset counters and data storage."""
        self.frame_count = 0
        self.frames_keypoints = []
        self.features_data = []

    async def process_video(self, frame):
        """Process a single frame and return data to broadcast."""
        if not self.is_trained:
            logger.error("Model not trained. Please train or load a model first.")
            return {"type": "error", "message": "Model not trained"}

        self.frame_count += 1
        annotated_frame = frame.copy()

        # Process the frame
        is_correct, feedback, features, errors = self.detect_form(annotated_frame)

        # Draw the pose on the frame
        frame_rgb = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(frame_rgb)
        annotated_frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        if results.pose_landmarks:
            # Extract landmarks and leading leg information
            leading_leg = features.get('leading_leg', 'Unknown') if features else 'Unknown'

            # Custom drawing to highlight only hips, knees, ankles
            landmarks = results.pose_landmarks

            # Create a custom connection list for hip-knee-ankle
            custom_connections = [
                (self.mp_pose.PoseLandmark.LEFT_HIP, self.mp_pose.PoseLandmark.LEFT_KNEE),
                (self.mp_pose.PoseLandmark.LEFT_KNEE, self.mp_pose.PoseLandmark.LEFT_ANKLE),
                (self.mp_pose.PoseLandmark.RIGHT_HIP, self.mp_pose.PoseLandmark.RIGHT_KNEE),
                (self.mp_pose.PoseLandmark.RIGHT_KNEE, self.mp_pose.PoseLandmark.RIGHT_ANKLE),
            ]

            # Highlight the leading leg with a different color
            left_color = (0, 255, 0) if leading_leg == "Left" else (255, 0, 0)  # Green for leading, blue for back
            right_color = (0, 255, 0) if leading_leg == "Right" else (255, 0, 0)

            # Draw only the landmarks we care about
            landmark_ids = [
                (self.mp_pose.PoseLandmark.LEFT_HIP, left_color),
                (self.mp_pose.PoseLandmark.LEFT_KNEE, left_color),
                (self.mp_pose.PoseLandmark.LEFT_ANKLE, left_color),
                (self.mp_pose.PoseLandmark.RIGHT_HIP, right_color),
                (self.mp_pose.PoseLandmark.RIGHT_KNEE, right_color),
                (self.mp_pose.PoseLandmark.RIGHT_ANKLE, right_color)
            ]

            for landmark_id, color in landmark_ids:
                landmark = landmarks.landmark[landmark_id]
                h, w, c = annotated_frame.shape
                cx, cy = int(landmark.x * w), int(landmark.y * h)
                cv2.circle(annotated_frame, (cx, cy), 10, color, -1)

            # Draw connections with correct colors
            for connection in [
                (self.mp_pose.PoseLandmark.LEFT_HIP, self.mp_pose.PoseLandmark.LEFT_KNEE, left_color),
                (self.mp_pose.PoseLandmark.LEFT_KNEE, self.mp_pose.PoseLandmark.LEFT_ANKLE, left_color),
                (self.mp_pose.PoseLandmark.RIGHT_HIP, self.mp_pose.PoseLandmark.RIGHT_KNEE, right_color),
                (self.mp_pose.PoseLandmark.RIGHT_KNEE, self.mp_pose.PoseLandmark.RIGHT_ANKLE, right_color),
            ]:
                start_idx = connection[0].value
                end_idx = connection[1].value
                connection_color = connection[2]

                start = landmarks.landmark[start_idx]
                end = landmarks.landmark[end_idx]

                h, w, c = annotated_frame.shape
                start_point = (int(start.x * w), int(start.y * h))
                end_point = (int(end.x * w), int(end.y * h))

                cv2.line(annotated_frame, start_point, end_point, connection_color, 3)

        # Display leading leg information
        if features and 'leading_leg' in features:
            cv2.putText(annotated_frame, f"Leading Leg: {features['leading_leg']}", 
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Display feedback
        color = (0, 255, 0) if is_correct else (0, 0, 255)
        cv2.putText(annotated_frame, feedback, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # Display errors with visual indicators
        if errors:
            y_pos = 90
            for feature_name, error_info in errors.items():
                message = error_info["message"]
                cv2.putText(annotated_frame, message, (10, y_pos), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                y_pos += 30
                # Log errors for report
                if message not in self.errors_log:
                    self.errors_log[message] = 0
                self.errors_log[message] += 1

        # Display features if available
        if features:
            h, w, c = annotated_frame.shape
            y_pos = h - 150  # Start from bottom of frame
            for feature_name, feature_value in features.items():
                if feature_name == 'leading_leg':
                    continue
                if isinstance(feature_value, (int, float)):
                    value_str = f"{feature_value:.1f}"
                else:
                    value_str = str(feature_value)
                cv2.putText(annotated_frame, f"{feature_name}: {value_str}", (10, y_pos), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                y_pos += 20

        # Track correct frames
        correct_return = "Incorrect"
        if is_correct:
            self.correct_frames += 1
            correct_return = "Correct"

        # Encode frame as base64 and return data
        frame_base64 = self._encode_frame(annotated_frame)
        return {
            "type": "frame",
            "data": frame_base64,
            "is_correct": correct_return,
            "feedback": feedback,
            "errors": errors,
        }

    def _encode_frame(self, frame):
        """Encode frame as base64."""
        _, buffer = cv2.imencode('.jpg', frame)
        return base64.b64encode(buffer).decode('utf-8')

    def generate_report(self):
        """Generate and return an exercise report."""
        report = "\n--- Lunges Exercise Report ---\n"
        report += f"Total Frames Processed: {self.frame_count}\n"
        report += f"Frames with Keypoints Detected: {len(self.frames_keypoints)}\n"
        if self.features_data:
            report += "Feature Summary (example):\n"
            # Add summary stats if desired, e.g., average depth or knee angle
            for i, features in enumerate(self.features_data[:5]):  # Limit to first 5 for brevity
                report += f"  - Frame {i+1}: {features}\n"
            if len(self.features_data) > 5:
                report += f"  - ...and {len(self.features_data) - 5} more frames\n"
        else:
            report += "No features calculated (no keypoints detected).\n"
        report += "--------------------------------\n"
        return report
    
    def detect_form(self, frame):
        """Detect lunge form in a single frame."""
        if not self.is_trained:
            raise ValueError("Model not trained. Please train or load a model first.")
        
        keypoints, leading_leg = self.extract_keypoints(frame)
        if keypoints is None:
            return False, "No person detected", None, None
        
        # Normalize based on which leg is leading
        normalized_keypoints = self.normalize_side(keypoints, leading_leg)
        
        # Calculate features for specific feedback
        features = self.calculate_lunge_features(normalized_keypoints, leading_leg)
        
        # Prepare keypoints for prediction
        keypoints_scaled = self.scaler.transform(normalized_keypoints.reshape(1, -1))
        keypoints_pca = self.pca.transform(keypoints_scaled)
        
        # Make prediction
        prediction = self.model.predict(keypoints_pca)[0]
        score = self.model.score_samples(keypoints_pca)[0]
        
        # Check if form is correct
        is_correct = prediction == 1
        
        # Prepare feedback
        feedback = ""
        errors = {}
        
        if not is_correct:
            for feature_name, feature_value in features.items():
                if feature_name == 'leading_leg':
                    continue
                    
                if "front_knee_angle" in feature_name:
                    if feature_value < 70:
                        message = f"{leading_leg} leg: Bend your knee more."
                        errors[feature_name] = {"message": message, "value": feature_value, "ideal": 90}
                        feedback += message + " "
                    elif feature_value > 110:
                        message = f"{leading_leg} leg: Don't bend your knee too much."
                        errors[feature_name] = {"message": message, "value": feature_value, "ideal": 90}
                        feedback += message + " "

            if not feedback:
                feedback = "Form needs improvement. Check your overall posture."
        else:
            feedback = "Good form!"
        
        return is_correct, feedback, features, errors
    def __init__(self, exercise="Lunges", delay_seconds=3, target_reps=8, fps=30):
        # Initialize MediaPipe Pose
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )

        # Set exercise type
        self.exercise = exercise

        # Thresholds for lunges
        self.LUNGE_THRESHOLDS = {
            "knee_angle": (80, 100),  # Front knee should be around 90 degrees
            "back_knee_angle": (75, 115),  # Back knee angle
            "torso_uprightness": (70, 110),  # Torso should be upright
            "stance_width": (0.2, 0.6),  # Distance between feet (normalized)
            "hip_level": (0, 0.15),  # Hip should be level (relative displacement)
        }

        # Recording and rep counting settings
        self.fps = fps
        self.delay_frames = delay_seconds * fps  # delay before correction
        self.target_reps = target_reps  # Number of reps to detect
        self.frame_count = 0
        self.recording = False  # Now indicates correction active
        self.report = {
            "good_form_frames": 0,
            "error_counts": defaultdict(int)
        }

        # Rep counting variables
        self.reps = 0
        self.in_lunge_position = False
        self.lunge_depth_threshold = 0.05  # Threshold for detecting rep
        self.prev_knee_angle = None
        self.start_frame = 0
        
        # Depth tracking
        self.max_knee_bend = 180
        self.shallow_rep_detected = False
        
        # Track movement direction for better rep counting
        self.knee_angles_history = []
        self.direction = None  # 'down' or 'up'
        self.phase_frames = 0
        
        # Visibility threshold for landmarks
        self.visibility_threshold = 0.6

    def calculate_angle(self, p1, p2, p3):
        """Calculate the angle between three points in degrees."""
        a = np.array(p1)
        b = np.array(p2)
        c = np.array(p3)
        
        ba = a - b
        bc = c - b
        
        # Handle zero vectors
        if np.linalg.norm(ba) < 1e-6 or np.linalg.norm(bc) < 1e-6:
            return 0
            
        cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
        cosine_angle = np.clip(cosine_angle, -1.0, 1.0)  # Avoid numerical errors
        angle = np.arccos(cosine_angle) * 180 / np.pi
        return angle

    def check_landmark_visibility(self, landmarks, landmark_indexes):
        """Check if landmarks are visible."""
        for idx in landmark_indexes:
            if landmarks[idx].visibility < self.visibility_threshold:
                return False
        return True

    def check_lunges_form(self, landmarks):
        """Analyze lunges exercise and return errors."""
        errors = []

        # Important landmarks for lunges
        key_landmarks = [
            self.mp_pose.PoseLandmark.LEFT_HIP, 
            self.mp_pose.PoseLandmark.RIGHT_HIP,
            self.mp_pose.PoseLandmark.LEFT_KNEE, 
            self.mp_pose.PoseLandmark.RIGHT_KNEE,
            self.mp_pose.PoseLandmark.LEFT_ANKLE, 
            self.mp_pose.PoseLandmark.RIGHT_ANKLE,
            self.mp_pose.PoseLandmark.LEFT_SHOULDER, 
            self.mp_pose.PoseLandmark.RIGHT_SHOULDER
        ]
        
        # Check if all key landmarks are visible
        if not self.check_landmark_visibility(landmarks, key_landmarks):
            return ["Move fully into camera view"], 180

        # Extract key landmarks
        l_hip = [landmarks[self.mp_pose.PoseLandmark.LEFT_HIP].x, landmarks[self.mp_pose.PoseLandmark.LEFT_HIP].y]
        r_hip = [landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP].x, landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP].y]
        l_knee = [landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE].x, landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE].y]
        r_knee = [landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE].x, landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE].y]
        l_ankle = [landmarks[self.mp_pose.PoseLandmark.LEFT_ANKLE].x, landmarks[self.mp_pose.PoseLandmark.LEFT_ANKLE].y]
        r_ankle = [landmarks[self.mp_pose.PoseLandmark.RIGHT_ANKLE].x, landmarks[self.mp_pose.PoseLandmark.RIGHT_ANKLE].y]
        l_shoulder = [landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER].x, landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER].y]
        r_shoulder = [landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER].x, landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER].y]
        
        # Calculate leg angles
        left_knee_angle = self.calculate_angle(l_hip, l_knee, l_ankle)
        right_knee_angle = self.calculate_angle(r_hip, r_knee, r_ankle)

        # Fix for NaN angles
        if np.isnan(left_knee_angle):
            left_knee_angle = 180
        if np.isnan(right_knee_angle):
            right_knee_angle = 180
            
        # Determine which leg is front (has smaller angle = more bent)
        if left_knee_angle < right_knee_angle:
            front_knee_angle = left_knee_angle
            back_knee_angle = right_knee_angle
            front_is_left = True
        else:
            front_knee_angle = right_knee_angle
            back_knee_angle = left_knee_angle
            front_is_left = False
            
        # Calculate torso angle (relative to vertical)
        mid_hip = [(l_hip[0] + r_hip[0]) / 2, (l_hip[1] + r_hip[1]) / 2]
        mid_shoulder = [(l_shoulder[0] + r_shoulder[0]) / 2, (l_shoulder[1] + r_shoulder[1]) / 2]
        # Angle with vertical (0 is perfectly upright)
        torso_angle = self.calculate_angle([mid_hip[0], mid_hip[1] + 1], mid_hip, mid_shoulder)
        
        # Calculate stance width
        stance_width = np.linalg.norm(np.array(l_ankle) - np.array(r_ankle))
        
        # Calculate hip level (should be level in a good lunge)
        hip_level_diff = abs(l_hip[1] - r_hip[1])
        
        # Front knee should not extend past ankle (knee-over-toe check)
        if front_is_left:
            knee_past_toe = l_knee[0] < l_ankle[0]
            front_hip, front_knee, front_ankle = l_hip, l_knee, l_ankle
        else:
            knee_past_toe = r_knee[0] > r_ankle[0]
            front_hip, front_knee, front_ankle = r_hip, r_knee, r_ankle
        
        # Form checks - use thresholds from the LUNGE_THRESHOLDS dictionary
        min_knee_angle, max_knee_angle = self.LUNGE_THRESHOLDS["knee_angle"]
        if front_knee_angle > max_knee_angle:
            errors.append("Bend front knee more")
        elif front_knee_angle < min_knee_angle:
            errors.append("Front knee bent too much")
            
        if knee_past_toe:
            errors.append("Front knee past toes")
            
        min_back_knee, max_back_knee = self.LUNGE_THRESHOLDS["back_knee_angle"]
        if back_knee_angle > max_back_knee:
            errors.append("Bend back knee more")
        elif back_knee_angle < min_back_knee:
            errors.append("Back knee bent too much")
            
        min_torso, max_torso = self.LUNGE_THRESHOLDS["torso_uprightness"]
        if torso_angle < min_torso or torso_angle > max_torso:
            errors.append("Keep torso upright")
            
        _, max_hip_diff = self.LUNGE_THRESHOLDS["hip_level"]
        if hip_level_diff > max_hip_diff:
            errors.append("Keep hips level")
            
        min_stance, max_stance = self.LUNGE_THRESHOLDS["stance_width"]
        if stance_width < min_stance:
            errors.append("Increase stance width")
        elif stance_width > max_stance:
            errors.append("Reduce stance width")
        
        # Track front knee angle for rep detection
        self.knee_angles_history.append(front_knee_angle)
        if len(self.knee_angles_history) > 10:  # Keep history manageable
            self.knee_angles_history.pop(0)
        
        # Use a smoother method for rep counting
        self._update_rep_counting(front_knee_angle)
            
        return errors[:3], front_knee_angle  # Return top 3 errors and knee angle

    def _update_rep_counting(self, knee_angle):
        """Improved rep counting logic with direction tracking."""
        # Wait for enough history
        if len(self.knee_angles_history) < 5:
            return
            
        # Calculate smoothed angle and derivative
        smoothed_angle = sum(self.knee_angles_history[-5:]) / 5
        derivative = self.knee_angles_history[-1] - self.knee_angles_history[-5]
        
        # Detect direction
        prev_direction = self.direction
        if derivative < -3:  # Going down (knee angle decreasing)
            self.direction = 'down'
        elif derivative > 3:  # Going up (knee angle increasing)
            self.direction = 'up'
            
        # Track phase duration
        if prev_direction != self.direction and self.direction is not None:
            self.phase_frames = 0
        else:
            self.phase_frames += 1
            
        # Rep detection based on phases
        # Down phase
        if self.direction == 'down' and smoothed_angle < 110 and not self.in_lunge_position:
            self.in_lunge_position = True
            self.max_knee_bend = 180
            self.shallow_rep_detected = False
            
        # Track deepest bend
        if self.in_lunge_position:
            self.max_knee_bend = min(self.max_knee_bend, smoothed_angle)
            
        # Up phase - finishing a rep
        if self.direction == 'up' and smoothed_angle > 140 and self.in_lunge_position and self.phase_frames > 5:
            self.in_lunge_position = False
            
            # Count rep if it was deep enough
            if self.max_knee_bend < 110:
                self.reps += 1
                logger.info(f"Rep {self.reps} counted, depth: {self.max_knee_bend:.1f}°")
            else:
                self.shallow_rep_detected = True
                logger.info(f"Shallow rep detected: {self.max_knee_bend:.1f}°")

    def reset_counters(self):
        """Reset counters and recording state."""
        self.frame_count = 0
        self.recording = False
        self.start_frame = 0
        self.reps = 0
        self.in_lunge_position = False
        self.prev_knee_angle = None
        self.max_knee_bend = 180
        self.shallow_rep_detected = False
        self.report = {
            "good_form_frames": 0,
            "error_counts": defaultdict(int)
        }
        self.knee_angles_history = []
        self.direction = None
        self.phase_frames = 0
        print(f"{self.exercise} analyzer counters reset")

    async def process_video(self, frame):
        """Process a single frame and return data to broadcast."""
        try:
            # Process the frame with MediaPipe Pose
            results = self.pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            annotated_frame = frame.copy()  # Create a copy to annotate

            if results.pose_landmarks:
                self.mp_drawing.draw_landmarks(annotated_frame, results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS)
                self.frame_count += 1

                # Display countdown during delay
                if self.frame_count <= self.delay_frames:
                    countdown = int(self.delay_frames / self.fps) - int(self.frame_count / self.fps)
                    cv2.putText(annotated_frame, f"Starting in: {countdown}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                else:
                    # Start correction after delay
                    if not self.recording:
                        self.recording = True
                        self.start_frame = self.frame_count

                    # Call form check method
                    errors, knee_angle = self.check_lunges_form(results.pose_landmarks.landmark)

                    # Record form data during correction
                    if self.recording:
                        if not errors:
                            self.report["good_form_frames"] += 1
                        for error in errors:
                            self.report["error_counts"][error] += 1

                    # Display feedback after delay
                    if self.recording:
                        if errors:
                            for i, error in enumerate(errors):
                                cv2.putText(annotated_frame, error, (10, 30 + i * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        else:
                            cv2.putText(annotated_frame, "Correct Form", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                    # Display rep count
                    cv2.putText(annotated_frame, f"Reps: {self.reps}/{self.target_reps}", (10, annotated_frame.shape[0] - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            # Encode frame as base64 and return data
            frame_base64 = self._encode_frame(annotated_frame)
            return {
                "type": "frame",
                "frame": frame_base64,
                "reps": self.reps,
                "target_reps": self.target_reps,
                "good_form_frames": self.report["good_form_frames"],
                "error_counts": dict(self.report["error_counts"]),  # Convert defaultdict to dict for serialization
                "recording": self.recording,
                "frame_count": self.frame_count - self.start_frame if self.recording else 0
            }
        except Exception as e:
            logger.error(f"Error processing video frame: {str(e)}")
            # Return a minimal response on error
            return {
                "type": "error",
                "error": f"Processing error: {str(e)}"
            }

    def _encode_frame(self, frame):
        """Encode frame as base64."""
        _, buffer = cv2.imencode('.jpg', frame)
        return base64.b64encode(buffer).decode('utf-8')

    def generate_report(self):
        """Generate and return an exercise report."""
        if not self.recording or self.frame_count <= self.start_frame:
            return "No exercise session recorded yet."
            
        total_recorded_frames = self.frame_count - self.start_frame  # Frames from start of correction
        if total_recorded_frames <= 0:
            return "No frames recorded yet."
            
        good_form_seconds = self.report["good_form_frames"] / self.fps
        total_seconds = total_recorded_frames / self.fps
    
        report_text = f"\n--- {self.exercise} Exercise Report ---\n"
        report_text += f"Total Recorded Time: {total_seconds:.2f} seconds\n"
        report_text += f"Good Form Duration: {good_form_seconds:.2f} seconds ({(good_form_seconds / total_seconds) * 100:.1f}%)\n"
        report_text += f"Repetitions Completed: {self.reps}/{self.target_reps}\n"
        
        if self.reps >= self.target_reps:
            report_text += "Goal achieved! 🎉\n"
        
        report_text += "\nErrors Detected:\n"
        if self.report["error_counts"]:
            # Sort errors by frequency
            sorted_errors = sorted(
                self.report["error_counts"].items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            for error, count in sorted_errors:
                error_seconds = count / self.fps
                report_text += f"  - '{error}': {count} frames ({error_seconds:.2f} seconds, {(count / total_recorded_frames) * 100:.1f}%)\n"
        else:
            report_text += "  - No errors detected! Perfect form!\n"
        
        report_text += "\nAreas to Focus On:\n"
        if self.report["error_counts"]:
            # Get top frequent error
            top_errors = sorted_errors[:1]
            for error, _ in top_errors:
                if "knee" in error.lower():
                    report_text += "  - Work on proper knee alignment and depth\n"
                elif "torso" in error.lower():
                    report_text += "  - Practice maintaining an upright torso position\n"
                elif "hip" in error.lower():
                    report_text += "  - Focus on keeping hips level throughout the movement\n"
                elif "stance" in error.lower():
                    report_text += "  - Adjust your stance width for better stability\n"
                else:
                    report_text += f"  - Practice proper form for: {error}\n"
        else:
            report_text += "  - Continue with your excellent form!\n"
            
        report_text += "--------------------------------\n"
        
        # Print the report too
        print(report_text)
        
        return report_text

    def __del__(self):
        """Clean up resources when the object is deleted."""
        try:
            if hasattr(self, 'pose'):
                self.pose.close()
        except Exception as e:
            print(f"Error closing pose: {e}")