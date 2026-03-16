# Azure OpenAI Geocoding Fallback

## Overview

The geocoding service now includes Azure OpenAI as a fallback when Nominatim fails to find coordinates. This helps geocode locations that Nominatim cannot resolve, especially for Jordan/Amman-specific locations.

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install `openai==0.28.1` which is compatible with Azure OpenAI.

### 2. Configure Environment Variables

Add these to your `.env` file:

```env
AZURE_OPENAI_KEY=your_azure_openai_key_here
AZURE_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_API_VERSION=2023-05-15
AZURE_DEPLOYMENT_NAME=gpt-4o
```

### 3. How It Works

1. **Primary Method**: Nominatim API (free, rate-limited to 1 req/sec)
2. **Fallback Method**: Azure OpenAI (when Nominatim fails)

The geocoding service will:
- First try Nominatim with various fallback strategies
- If all Nominatim attempts fail, it will try Azure OpenAI
- Azure OpenAI uses GPT-4o to intelligently find coordinates for locations

## Usage

### Automatic Usage

The Azure OpenAI fallback is **automatically used** when:
- Running `scripts/enrich_csv_with_coordinates.py`
- Importing CSV with `--geocode-missing` flag
- Any code that uses `geocoding_service.get_coordinates_with_fallback()`

### Example: Enrich CSV with Coordinates

```bash
# This will use Nominatim first, then Azure OpenAI for failed locations
python scripts/enrich_csv_with_coordinates.py data\abdoun_merged_properties.csv
```

### Example: Import CSV with Geocoding

```bash
# This will geocode missing coordinates during import
python scripts/import_from_csv.py data\abdoun_merged_properties.csv --geocode-missing
```

## Features

**Non-breaking**: Existing Nominatim geocoding continues to work  
**Automatic**: No code changes needed, just configure .env  
**Smart Fallback**: Only uses Azure OpenAI when Nominatim fails  
**Cost-effective**: Minimizes Azure OpenAI API calls  
**Logging**: Shows when Azure OpenAI is being used  

## Cost Considerations

- Azure OpenAI is only called when Nominatim fails
- Each failed location = 1 API call to Azure OpenAI
- Monitor your Azure OpenAI usage in the Azure portal

## Troubleshooting

### Azure OpenAI Not Working

1. Check that all 4 environment variables are set in `.env`
2. Verify your Azure OpenAI credentials are correct
3. Check that the deployment name matches your Azure resource
4. Ensure you have credits/quota in your Azure OpenAI account

### Still Getting Failures

Some locations may genuinely not exist or be too ambiguous. The service will:
- Log all attempts
- Show which method was used (Nominatim vs Azure OpenAI)
- Report success/failure rates in the summary

## Example Output

```
[1588/2358] Geocoding: Dair Gbhar - Amman
    Not found (Nominatim failed)
    Trying Azure OpenAI as final fallback for: 'Dair Gbhar - Amman'
    Azure OpenAI geocoded 'Dair Gbhar - Amman' to (31.953900, 35.910600)
```

