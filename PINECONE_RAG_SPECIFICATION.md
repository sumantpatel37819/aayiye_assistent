# 🌲 Pinecone Vector RAG — Complete Technical Specification
**Author / Source**: Aayie Chatbot & Tour RAG Pipeline  
**Target Consumer**: `tourKaro_reDesign` (Chatbot & Backend Integration)

---

## 1. 📌 Overview & Quick Facts

| Property | Value / Configuration |
|---|---|
| **Vector DB Provider** | **Pinecone Serverless** |
| **Index Name** | `sonukumar` *(Note: lowercase in API calls)* |
| **Index Host Endpoint** | `https://sonukumar-8ggt3xq.svc.aped-4627-b74a.pinecone.io` |
| **Cloud & Region** | `aws` / `us-east-1` |
| **Vector Dimensions** | **`1024`** |
| **Distance Metric** | **`cosine`** |
| **Current Records Loaded** | **356 verified destinations** (Bihar state) |
| **ID Format** | `{state_slug}_{place_id}` (e.g. `bihar_1`, `bihar_2`, ...) |

---

## 2. 🧠 Embedding Model Details

| Property | Value |
|---|---|
| **Model Name** | **`mxbai-embed-large`** (MixedBread AI) |
| **Ollama Local Tag** | `mxbai-embed-large:latest` (Port `11434`) |
| **Hugging Face Model ID** | `mixedbread-ai/mxbai-embed-large` |
| **Output Dimension** | `1024` float array |
| **Query Prefix Rule** | When embedding a user question, prefix with: <br>`"Represent this sentence for searching relevant passages: "` |

---

## 3. 📦 Vector Metadata Schema

Every vector in Pinecone has `metadata` attached to it so the search result returns full place facts without requiring secondary database queries:

```json
{
  "place_id": 1,
  "name": "Golghar",
  "state": "Bihar",
  "city": "Patna",
  "category": "Historical Monument",
  "other_names": "Round House Patna",
  "lat": 25.6207,
  "lng": 85.1386,
  "opening_hour": "10:00 AM - 05:00 PM (Closed on Monday)",
  "avg_time_spend": "1 to 2 hours",
  "entry_fee": "Rs 20 for Indians, Rs 100 for Foreigners, Free for children below 5",
  "best_time_to_visit": "October to March (Ideal visiting hours: 4:00 PM - 5:30 PM for sunset)",
  "text": "Destination: Golghar (Round House Patna) (Historical Monument)\nLocation: Patna, Bihar | Coordinates: 25.6207, 85.1386\nOperating Timings: 10:00 AM - 05:00 PM (Closed on Monday)\nEntry Fee & Tickets: Rs 20 for Indians, Rs 100 for Foreigners, Free for children below 5\nRecommended Duration: 1 to 2 hours\nBest Time to Visit & Traveler Suitability: October to March\nAbout the Place: A massive beehive-shaped granary built by Captain John Garstin in 1786..."
}
```

### Metadata Fields Explanation:
- `name`: Primary title of the destination.
- `city` & `state`: Geographic location (can be used for Pinecone Metadata Filtering: `{"city": {"$eq": "Patna"}}`).
- `category`: Type of spot (Historical, Eco-Tourism, Temple, Museum, Fort, Waterfalls).
- `entry_fee`: Exact entry ticket prices and concessions.
- `opening_hour`: Exact opening days, closing day, and opening/closing hours.
- `avg_time_spend`: Recommended stay duration for itinerary generation.
- `best_time_to_visit`: Seasonal guidance, weather suitability, and optimal time of day.
- `text`: Complete formatted semantic chunk ready to inject directly into Gemini / Llama prompt context!

---

## 4. 🔍 How to Query from JavaScript (Node.js / Express)

In `tourKaro_reDesign`, you can query Pinecone using standard `axios` in 2 simple steps:

### Step 1: Embed Query via Ollama or Hugging Face
```javascript
const axios = require('axios');

async function getEmbedding(queryText) {
  const prompt = `Represent this sentence for searching relevant passages: ${queryText.trim()}`;

  // Option A: Local Ollama (Local Development)
  if (process.env.NODE_ENV !== 'production') {
    try {
      const res = await axios.post('http://127.0.0.1:11434/api/embeddings', {
        model: 'mxbai-embed-large',
        prompt: prompt
      }, { timeout: 4000 });
      return res.data.embedding; // 1024 floats
    } catch (e) {
      console.warn('Local Ollama unavailable, using Cloud fallback...');
    }
  }

  // Option B: Hugging Face Cloud Inference (Production on Render)
  const res = await axios.post(
    'https://api-inference.huggingface.co/models/mixedbread-ai/mxbai-embed-large',
    { inputs: prompt },
    {
      headers: {
        'Authorization': `Bearer ${process.env.HF_TOKEN}`,
        'Content-Type': 'application/json'
      },
      timeout: 5000
    }
  );
  return res.data; // 1024 floats
}
```

### Step 2: Query Pinecone REST API
```javascript
async function searchPlacesInPinecone(queryText, topK = 4, cityFilter = null) {
  const vector = await getEmbedding(queryText);

  const payload = {
    vector,
    topK,
    includeMetadata: true
  };

  // Optional city filter
  if (cityFilter) {
    payload.filter = { city: { '$eq': cityFilter.trim() } };
  }

  const pineconeRes = await axios.post(
    'https://sonukumar-8ggt3xq.svc.aped-4627-b74a.pinecone.io/query',
    payload,
    {
      headers: {
        'Api-Key': process.env.PINECONE_API_KEY,
        'Content-Type': 'application/json'
      },
      timeout: 5000
    }
  );

  const matches = pineconeRes.data?.matches || [];
  return matches.map(m => ({
    score: m.score,
    place: m.metadata
  }));
}
```

---

## 5. 🤖 Injecting into Gemini Chatbot Prompt

When calling Gemini (`gemini-2.5-flash`):
```javascript
const placesContext = searchResults
  .map(r => r.place.text)
  .join('\n\n---\n\n');

const systemInstruction = `
You are TourKaro AI — an expert Indian Travel & Tourism Assistant.
Answer the user query accurately and conversationally using the verified destination facts provided below.
Mention exact timings, entry ticket costs, and travel tips when relevant.

Verified Tourist Places Context:
${placesContext}
`;
```

---

## 6. 🔑 Environment Variables Needed
```env
PINECONE_API_KEY=pcsk_25wPMM_AQQQFG2yGzs9ZJBLQUuTgu6zid7CseGTzaqsS2iAKq4Hbr9deRKo85qBCiBzVjJ
PINECONE_INDEX_HOST=https://sonukumar-8ggt3xq.svc.aped-4627-b74a.pinecone.io
PINECONE_INDEX_NAME=sonukumar
```
*(Plus `HF_TOKEN` if using Hugging Face inference on Render without local Ollama).*
