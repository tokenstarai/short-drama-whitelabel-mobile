import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../flavor/flavor.dart';

class SplashHeader extends StatelessWidget {
  const SplashHeader({required this.flavor, super.key});

  final FlavorConfig flavor;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 8),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: runtime.effectiveBrandPrimaryColor,
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Icon(Icons.play_arrow_rounded, color: Colors.white),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  runtime.appName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const Text(
                  'Tenant edge ready',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: Colors.black54),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
