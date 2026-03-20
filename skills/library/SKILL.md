# OSGeo Document Library Skill

You have access to the osgeo-library MCP server with tools to search and
browse a collection of geospatial and scientific documents.

## Available tools

- osgeo-library_list_documents -- list all documents
- osgeo-library_search_documents -- semantic/keyword search
- osgeo-library_search_visual_elements -- search figures, tables, equations
- osgeo-library_get_element_details -- get full metadata for an element
- osgeo-library_find_document -- find a document by name
- osgeo-library_get_document_info -- detailed document metadata
- osgeo-library_list_elements -- list elements in a document
- osgeo-library_get_page_metadata -- page-level metadata
- osgeo-library_get_page_image -- get a full page as an image
- osgeo-library_get_element_image -- get a figure/table/equation as an image

## Showing images

When the user asks you to show an image, figure, table, or page:

1. Use get_page_image or get_element_image to retrieve it
2. The tool returns BOTH a text description AND an image
3. The image is automatically displayed in the chat by the bridge
4. In your text reply, describe what the image shows but do NOT say
   you cannot display it -- the bridge handles image rendering
5. If the tool returns an image, it WILL be visible to the user

## Search workflow

1. Start with search_documents or search_visual_elements
2. Results include document_slug and element labels
3. Use get_element_image(document_slug, element_label) to show a result
4. Use get_page_image(document_slug, page_number) for full pages

## Tips

- Element labels look like: "Figure 1", "Table 3-2", "Equation 5"
- Document slugs look like: "usgs_snyder", "torchgeo", "landsat_manual_v5"
- When listing documents, group them by topic for readability
- Keep descriptions concise -- the image speaks for itself
