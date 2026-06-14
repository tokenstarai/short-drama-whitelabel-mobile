import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../flavor/flavor.dart';
import '../drama_detail/drama_detail_screen.dart';

class CatalogScreen extends StatelessWidget {
  const CatalogScreen({
    required this.flavor,
    this.catalog = const [],
    super.key,
  });

  final FlavorConfig flavor;
  final List<CatalogDrama> catalog;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final items = catalog.isEmpty
        ? const [
            CatalogDrama(
              dramaId: 'drama_1',
              title: 'Seed Drama',
              posterUrl: '/assets/posters/1.png',
              episodeCount: 12,
              readyEpisodeCount: 3,
              pointPrice: 2,
            ),
          ]
        : catalog;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Catalog', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 12),
        const Wrap(
          spacing: 8,
          children: [
            FilterChip(label: Text('Hot'), onSelected: null),
            FilterChip(label: Text('Latest'), onSelected: null),
            FilterChip(label: Text('Romance'), onSelected: null),
            FilterChip(label: Text('SEA'), onSelected: null),
          ],
        ),
        const SizedBox(height: 16),
        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            childAspectRatio: 0.68,
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
          ),
          itemCount: items.length,
          itemBuilder: (context, index) {
            final drama = items[index];
            return InkWell(
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => DramaDetailScreen(
                    flavor: flavor,
                    dramaId: drama.dramaId,
                    drama: drama,
                  ),
                ),
              ),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Container(
                        decoration: BoxDecoration(
                          color: runtime.effectiveBrandPrimaryColor
                              .withValues(alpha: 0.16),
                          borderRadius: const BorderRadius.vertical(
                            top: Radius.circular(12),
                          ),
                        ),
                        child: const Center(
                          child: Icon(Icons.movie_creation_outlined, size: 36),
                        ),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.all(10),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            drama.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 4),
                          Text(
                            '${drama.readyEpisodeCount}/${drama.episodeCount} ready · ${drama.pointPrice} coins',
                            style: const TextStyle(
                              fontSize: 12,
                              color: Colors.black54,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      ],
    );
  }
}
