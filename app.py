import os
import sys
import json
import base64
from datetime import datetime
import hashlib
import uuid
import requests
import io

# DON'T CHANGE THIS PATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_from_directory, send_file, redirect
from flask_cors import CORS
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

app.config['SECRET_KEY'] = 'your-secret-key-here'

# Debug: Print environment variables (without secrets)
print("=== CLOUDINARY CONFIGURATION DEBUG ===")
cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
api_key = os.getenv('CLOUDINARY_API_KEY')
api_secret = os.getenv('CLOUDINARY_API_SECRET')

print(f"CLOUDINARY_CLOUD_NAME: {'✅ SET' if cloud_name else '❌ MISSING'}")
print(f"CLOUDINARY_API_KEY: {'✅ SET' if api_key else '❌ MISSING'}")
print(f"CLOUDINARY_API_SECRET: {'✅ SET' if api_secret else '❌ MISSING'}")

# Configure Cloudinary
cloudinary_configured = False
if cloud_name and api_key and api_secret:
    try:
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret
        )
        # Test Cloudinary connection
        cloudinary.api.ping()
        cloudinary_configured = True
        print("✅ CLOUDINARY: Successfully configured and connected!")
    except Exception as e:
        print(f"❌ CLOUDINARY: Configuration failed - {e}")
        cloudinary_configured = False
else:
    print("❌ CLOUDINARY: Missing environment variables")
    cloudinary_configured = False

print(f"CLOUDINARY STATUS: {'✅ READY' if cloudinary_configured else '❌ NOT CONFIGURED'}")
print("==========================================")

# Local metadata files for fallback
LOCAL_METADATA_FILE = 'photos_data.json'
LOCAL_COLLECTIONS_FILE = 'collections_data.json'

def load_photos_from_cloudinary():
    """Load photos metadata from Cloudinary by listing resources"""
    if not cloudinary_configured:
        print("⚠️ Cloudinary not configured, using local metadata only")
        return []
    
    try:
        print("☁️ Loading photos from Cloudinary...")
        # Get all resources from the gallery folder
        result = cloudinary.api.resources(
            type="upload",
            prefix="georges_photo_gallery/",
            max_results=500,
            context=True
        )
        
        photos_data = []
        for resource in result.get('resources', []):
            # Extract metadata from context
            context = resource.get('context', {})
            
            # FIXED: Proper collection_id handling
            collection_id = context.get('collection_id', '')
            if collection_id and collection_id != '':
                try:
                    collection_id = int(collection_id)
                except (ValueError, TypeError):
                    collection_id = None
            else:
                collection_id = None
            
            photo_data = {
                'id': int(context.get('id', len(photos_data) + 1)),
                'filename': context.get('filename', 'photo.jpg'),
                'title': context.get('title', 'Untitled'),
                'description': context.get('description', ''),
                'collection_id': collection_id,  # FIXED: Properly converted
                'cloudinary_url': resource['secure_url'],
                'cloudinary_public_id': resource['public_id'],
                'image_url': resource['secure_url'],
                'upload_date': context.get('upload_date', resource.get('created_at', '')),
                'storage_type': 'cloudinary'
            }
            photos_data.append(photo_data)
        
        # Sort by ID
        photos_data.sort(key=lambda x: x['id'])
        print(f"✅ Loaded {len(photos_data)} photos from Cloudinary")
        return photos_data
        
    except Exception as e:
        print(f"⚠️ Error loading from Cloudinary: {e}")
        return []

def load_collections_from_cloudinary():
    """Load collections metadata from Cloudinary"""
    if not cloudinary_configured:
        print("⚠️ Cloudinary not configured, skipping collections download")
        return []
    
    try:
        print("☁️ Loading collections from Cloudinary...")
        # Try to get collections metadata from Cloudinary
        result = cloudinary.api.resource(
            "georges_photo_gallery/collections_metadata",
            resource_type="raw"
        )
        
        print(f"📄 Found collections file: {result.get('secure_url', 'URL not available')}")
        
        # Download the JSON file
        response = requests.get(result['secure_url'])
        response.raise_for_status()
        
        collections_data = response.json()
        print(f"✅ Loaded {len(collections_data)} collections from Cloudinary")
        return collections_data
        
    except Exception as e:
        if "404" in str(e) or "Resource not found" in str(e):
            print(f"⚠️ Collections not found in Cloudinary: {e}")
        else:
            print(f"⚠️ Error loading collections from Cloudinary: {e}")
        return []

def save_collections_to_cloudinary(collections_data):
    """Save collections metadata to Cloudinary"""
    if not cloudinary_configured:
        print("⚠️ Cloudinary not configured, skipping collections upload")
        return False
    
    try:
        print("☁️ Saving collections to Cloudinary...")
        
        # Convert to JSON string
        collections_json = json.dumps(collections_data, indent=2)
        print(f"📄 JSON size: {len(collections_json)} characters")
        
        # Create a file-like object from the JSON string
        json_file = io.BytesIO(collections_json.encode('utf-8'))
        
        # Upload as raw file with explicit content type
        upload_result = cloudinary.uploader.upload(
            json_file,
            public_id="collections_metadata",
            folder="georges_photo_gallery",
            resource_type="raw",
            overwrite=True,
            content_type="application/json"
        )
        
        print(f"✅ Collections saved to Cloudinary: {upload_result.get('secure_url', 'URL not available')}")
        return True
        
    except Exception as e:
        print(f"❌ Error saving collections to Cloudinary: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return False

def load_photos_data():
    """Load photos metadata from Cloudinary first, then local fallback"""
    # Try Cloudinary first
    cloudinary_data = load_photos_from_cloudinary()
    if cloudinary_data:
        # Save to local file as cache
        try:
            with open(LOCAL_METADATA_FILE, 'w') as f:
                json.dump(cloudinary_data, f, indent=2)
            print("💾 Cached photos metadata locally")
        except:
            pass
        return cloudinary_data
    
    # Fallback to local file
    try:
        if os.path.exists(LOCAL_METADATA_FILE):
            with open(LOCAL_METADATA_FILE, 'r') as f:
                data = json.load(f)
                print(f"📁 Loaded {len(data)} photos from local cache")
                return data
        print("📁 No existing photos metadata found")
        return []
    except Exception as e:
        print(f"❌ Error loading photos metadata: {e}")
        return []

def load_collections_data():
    """Load collections metadata from Cloudinary first, then local fallback"""
    # Try Cloudinary first
    cloudinary_data = load_collections_from_cloudinary()
    if cloudinary_data:
        # Save to local file as cache
        try:
            with open(LOCAL_COLLECTIONS_FILE, 'w') as f:
                json.dump(cloudinary_data, f, indent=2)
            print("💾 Cached collections metadata locally")
        except:
            pass
        return cloudinary_data
    
    # Fallback to local file
    try:
        if os.path.exists(LOCAL_COLLECTIONS_FILE):
            with open(LOCAL_COLLECTIONS_FILE, 'r') as f:
                data = json.load(f)
                print(f"📁 Loaded {len(data)} collections from local cache")
                return data
        print("📁 No existing collections metadata found")
        return []
    except Exception as e:
        print(f"❌ Error loading collections metadata: {e}")
        return []

def save_collections_data(collections_data):
    """Save collections metadata to both Cloudinary and local"""
    print(f"💾 Saving {len(collections_data)} collections...")
    
    # Save to Cloudinary first
    cloudinary_success = False
    if cloudinary_configured:
        cloudinary_success = save_collections_to_cloudinary(collections_data)
        if cloudinary_success:
            print("✅ Collections successfully saved to Cloudinary")
        else:
            print("❌ Failed to save collections to Cloudinary")
    else:
        print("⚠️ Cloudinary not configured, skipping cloud save")
    
    # Save to local file as backup
    local_success = False
    try:
        with open(LOCAL_COLLECTIONS_FILE, 'w') as f:
            json.dump(collections_data, f, indent=2)
        print("💾 Collections saved locally")
        local_success = True
    except Exception as e:
        print(f"❌ Error saving collections locally: {e}")
    
    # Return success status
    if cloudinary_configured:
        return cloudinary_success
    else:
        return local_success

def get_next_photo_id():
    """Get the next available photo ID"""
    photos_data = load_photos_data()
    if not photos_data:
        return 1
    return max(photo['id'] for photo in photos_data) + 1

def get_next_collection_id():
    """Get the next available collection ID"""
    collections_data = load_collections_data()
    if not collections_data:
        return 1
    return max(collection['id'] for collection in collections_data) + 1

def get_collection_photo_count(collection_id):
    """Get the number of photos in a collection"""
    photos_data = load_photos_data()
    return len([p for p in photos_data if p.get('collection_id') == collection_id])

def get_collection_name(collection_id):
    """Get collection name by ID"""
    if not collection_id:
        return None
    collections_data = load_collections_data()
    collection = next((c for c in collections_data if c['id'] == collection_id), None)
    return collection['name'] if collection else None

# Debug endpoint
@app.route('/api/debug')
def debug_info():
    """Debug endpoint to check configuration"""
    photos_data = load_photos_data()
    collections_data = load_collections_data()
    return jsonify({
        'cloudinary_configured': cloudinary_configured,
        'environment_variables': {
            'CLOUDINARY_CLOUD_NAME': '✅ SET' if os.getenv('CLOUDINARY_CLOUD_NAME') else '❌ MISSING',
            'CLOUDINARY_API_KEY': '✅ SET' if os.getenv('CLOUDINARY_API_KEY') else '❌ MISSING',
            'CLOUDINARY_API_SECRET': '✅ SET' if os.getenv('CLOUDINARY_API_SECRET') else '❌ MISSING'
        },
        'json_file_exists': os.path.exists(LOCAL_METADATA_FILE),
        'photos_count': len(photos_data),
        'collections_count': len(collections_data),
        'storage_type': 'cloudinary' if cloudinary_configured else 'local'
    })

# Collections API Routes
@app.route('/api/collections', methods=['GET'])
def get_collections():
    try:
        collections_data = load_collections_data()
        
        # Add photo count to each collection
        for collection in collections_data:
            collection['photo_count'] = get_collection_photo_count(collection['id'])
        
        return jsonify({
            'success': True,
            'collections': collections_data
        })
    except Exception as e:
        print(f"❌ Error getting collections: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/collections', methods=['POST'])
def create_collection():
    try:
        # Verify admin password
        password = request.headers.get('X-Admin-Password')
        if password != 'Hanshow99@':
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'success': False, 'error': 'Collection name is required'}), 400
        
        collections_data = load_collections_data()
        
        # Check if name already exists
        if any(c['name'].lower() == name.lower() for c in collections_data):
            return jsonify({'success': False, 'error': 'Collection name already exists'}), 400
        
        # Create new collection
        new_collection = {
            'id': get_next_collection_id(),
            'name': name,
            'created_date': datetime.now().isoformat()
        }
        
        collections_data.append(new_collection)
        
        # Save collections
        if save_collections_data(collections_data):
            print(f"📁 Created collection: {name}")
            return jsonify({'success': True, 'collection': new_collection})
        else:
            return jsonify({'success': False, 'error': 'Failed to save collection'}), 500
        
    except Exception as e:
        print(f"❌ Error creating collection: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/collections/<int:collection_id>/photos', methods=['GET'])
def get_collection_photos(collection_id):
    try:
        photos_data = load_photos_data()
        collections_data = load_collections_data()
        
        # Find collection
        collection = next((c for c in collections_data if c['id'] == collection_id), None)
        if not collection:
            return jsonify({'success': False, 'error': 'Collection not found'}), 404
        
        # Filter photos by collection (handle both string and integer collection_id)
        collection_photos = []
        for photo in photos_data:
            photo_collection_id = photo.get('collection_id')
            if photo_collection_id is not None:
                # Convert both to string for comparison to handle type mismatches
                if str(photo_collection_id) == str(collection_id):
                    collection_photos.append(photo)
        
        # Sort by upload_date descending
        collection_photos.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
        
        print(f"📁 Collection {collection_id} ({collection['name']}): Found {len(collection_photos)} photos")
        
        return jsonify({
            'success': True,
            'photos': collection_photos,
            'collection': collection,
            'total_count': len(collection_photos)
        })
        
    except Exception as e:
        print(f"❌ Error getting collection photos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/collections/<int:collection_id>', methods=['PUT'])
def update_collection(collection_id):
    try:
        # Verify admin password
        password = request.headers.get('X-Admin-Password')
        if password != 'Hanshow99@':
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'success': False, 'error': 'Collection name is required'}), 400
        
        collections_data = load_collections_data()
        collection = next((c for c in collections_data if c['id'] == collection_id), None)
        
        if not collection:
            return jsonify({'success': False, 'error': 'Collection not found'}), 404
        
        # Check if name already exists (excluding current collection)
        if any(c['name'].lower() == name.lower() and c['id'] != collection_id for c in collections_data):
            return jsonify({'success': False, 'error': 'Collection name already exists'}), 400
        
        # Update collection
        collection['name'] = name
        
        # Save collections
        if save_collections_data(collections_data):
            print(f"📁 Updated collection: {name}")
            return jsonify({'success': True, 'collection': collection})
        else:
            return jsonify({'success': False, 'error': 'Failed to save collection'}), 500
        
    except Exception as e:
        print(f"❌ Error updating collection: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/photos/<int:photo_id>/collection', methods=['PUT'])
def update_photo_collection(photo_id):
    try:
        # Verify admin password
        password = request.headers.get('X-Admin-Password')
        if password != 'Hanshow99@':
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        collection_id = data.get('collection_id')
        
        # Validate collection if provided
        if collection_id:
            collections_data = load_collections_data()
            if not any(c['id'] == int(collection_id) for c in collections_data):
                return jsonify({'success': False, 'error': 'Invalid collection ID'}), 400
            collection_id = int(collection_id)
        
        photos_data = load_photos_data()
        photo = next((p for p in photos_data if p['id'] == photo_id), None)
        
        if not photo:
            return jsonify({'success': False, 'error': 'Photo not found'}), 404
        
        # Update photo collection in Cloudinary if configured
        if cloudinary_configured and 'cloudinary_public_id' in photo:
            try:
                context = {
                    'id': str(photo['id']),
                    'filename': photo['filename'],
                    'title': photo['title'],
                    'description': photo['description'],
                    'collection_id': str(collection_id) if collection_id else '',
                    'upload_date': photo['upload_date']
                }
                
                cloudinary.uploader.explicit(
                    photo['cloudinary_public_id'],
                    type="upload",
                    context=context
                )
                
                print(f"✅ Updated photo collection in Cloudinary: {photo['title']}")
                
            except Exception as e:
                print(f"⚠️ Error updating photo context in Cloudinary: {e}")
                return jsonify({'success': False, 'error': 'Failed to update photo in Cloudinary'}), 500
        
        # Update photo collection in local data
        photo['collection_id'] = collection_id
        
        # Update local cache
        try:
            with open(LOCAL_METADATA_FILE, 'w') as f:
                json.dump(photos_data, f, indent=2)
            print(f"💾 Updated local photos cache")
        except Exception as e:
            print(f"⚠️ Error updating local cache: {e}")
        
        print(f"📸 Updated photo collection: {photo['title']} -> Collection {collection_id}")
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Error updating photo collection: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Photos API Routes (Updated with Collections Support)
@app.route('/api/photos', methods=['GET'])
def get_photos():
    try:
        photos_data = load_photos_data()
        collections_data = load_collections_data()
        
        # Add collection name to photos
        for photo in photos_data:
            if photo.get('collection_id'):
                photo['collection_name'] = get_collection_name(photo['collection_id'])
        
        return jsonify({
            'success': True,
            'photos': photos_data
        })
    except Exception as e:
        print(f"❌ Error getting photos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/photos', methods=['POST'])
def upload_photo():
    try:
        # Verify admin password
        password = request.headers.get('X-Admin-Password')
        if password != 'Hanshow99@':
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        # Get form data
        title = request.form.get('title', 'Untitled')
        description = request.form.get('description', '')
        collection_id = request.form.get('collection_id')
        
        # Validate collection if provided
        if collection_id:
            try:
                collection_id = int(collection_id)
                collections_data = load_collections_data()
                if not any(c['id'] == collection_id for c in collections_data):
                    return jsonify({'success': False, 'error': 'Invalid collection ID'}), 400
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid collection ID format'}), 400
        else:
            collection_id = None
        
        # Check if file is provided
        if 'photo' not in request.files:
            return jsonify({'success': False, 'error': 'No photo file provided'}), 400
        
        file = request.files['photo']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No photo file selected'}), 400
        
        # Generate unique filename
        file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        
        # Get next photo ID
        photo_id = get_next_photo_id()
        
        # Upload to Cloudinary if configured
        if cloudinary_configured:
            try:
                # Prepare context metadata
                context = {
                    'id': str(photo_id),
                    'filename': file.filename,
                    'title': title,
                    'description': description,
                    'collection_id': str(collection_id) if collection_id else '',
                    'upload_date': datetime.now().isoformat()
                }
                
                print(f"📸 Uploading photo: {file.filename} (ID: {photo_id}, Collection: {collection_id})")
                
                # Upload to Cloudinary
                upload_result = cloudinary.uploader.upload(
                    file,
                    public_id=f"photo_{photo_id}_{unique_filename}",
                    folder="georges_photo_gallery",
                    context=context
                )
                
                print("✅ Cloudinary upload successful")
                
                # Create photo data
                photo_data = {
                    'id': photo_id,
                    'filename': file.filename,
                    'title': title,
                    'description': description,
                    'collection_id': collection_id,
                    'cloudinary_url': upload_result['secure_url'],
                    'cloudinary_public_id': upload_result['public_id'],
                    'image_url': upload_result['secure_url'],
                    'upload_date': datetime.now().isoformat(),
                    'storage_type': 'cloudinary'
                }
                
                print(f"✅ Metadata stored in context: {{'collection_id': '{collection_id}'}}")
                
                return jsonify({
                    'success': True,
                    'photo': photo_data
                })
                
            except Exception as e:
                print(f"❌ Cloudinary upload failed: {e}")
                return jsonify({'success': False, 'error': f'Upload failed: {str(e)}'}), 500
        else:
            return jsonify({'success': False, 'error': 'Cloudinary not configured'}), 500
            
    except Exception as e:
        print(f"❌ Error uploading photo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/photos/<int:photo_id>', methods=['DELETE'])
def delete_photo(photo_id):
    try:
        # Verify admin password
        password = request.headers.get('X-Admin-Password')
        if password != 'Hanshow99@':
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        photos_data = load_photos_data()
        photo = next((p for p in photos_data if p['id'] == photo_id), None)
        
        if not photo:
            return jsonify({'success': False, 'error': 'Photo not found'}), 404
        
        # Delete from Cloudinary if configured
        if cloudinary_configured and 'cloudinary_public_id' in photo:
            try:
                cloudinary.uploader.destroy(photo['cloudinary_public_id'])
                print(f"✅ Deleted from Cloudinary: {photo['title']}")
            except Exception as e:
                print(f"⚠️ Error deleting from Cloudinary: {e}")
        
        # Remove from local data
        photos_data = [p for p in photos_data if p['id'] != photo_id]
        
        # Save updated data
        try:
            with open(LOCAL_METADATA_FILE, 'w') as f:
                json.dump(photos_data, f, indent=2)
            print(f"💾 Updated local photos cache")
        except Exception as e:
            print(f"⚠️ Error updating local cache: {e}")
        
        print(f"🗑️ Deleted photo: {photo['title']}")
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Error deleting photo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Serve the main page
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# Serve static files
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    print("🚀 Running with gunicorn")
    print(f"📁 Static folder: {app.static_folder}")
    print(f"☁️ Cloudinary status: {'✅ CONFIGURED' if cloudinary_configured else '❌ NOT CONFIGURED'}")
    print(f"💾 Metadata storage: {'☁️ CLOUDINARY CONTEXT' if cloudinary_configured else '📁 LOCAL FILES'}")
    print(f"📁 Collections system: ✅ ENABLED")
    print("🎉 CLEAN VERSION: No Google Drive integration, collections working!")
    
    app.run(host='0.0.0.0', port=5002, debug=False)

